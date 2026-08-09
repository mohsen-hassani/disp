import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth.tokens import (
    ExpiredAccessTokenError,
    InvalidAccessTokenError,
    decode_access_token,
    hash_pat,
    is_pat,
)
from disp.core.config import get_settings
from disp.core.db import get_session
from disp.core.errors import AppError
from disp.core.models import ApiToken, User

_BEARER_RE = re.compile(r"^Bearer (.+)$")
PAT_LAST_USED_UPDATE_INTERVAL = timedelta(seconds=60)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: UUID
    email: str
    display_name: str
    is_admin: bool
    auth_method: Literal["access_token", "api_token"]
    token_id: UUID | None


def _missing_credentials_error() -> AppError:
    return AppError(
        status_code=401,
        code="core.auth.missing_credentials",
        title="Missing credentials",
        detail="An Authorization header is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _malformed_credentials_error() -> AppError:
    return AppError(
        status_code=401,
        code="core.auth.malformed_credentials",
        title="Malformed credentials",
        detail="The Authorization header must be of the form 'Bearer <token>'.",
    )


def _invalid_token_error() -> AppError:
    return AppError(
        status_code=401,
        code="core.auth.invalid_token",
        title="Invalid token",
        detail="The access token is invalid.",
    )


def _account_disabled_error() -> AppError:
    return AppError(
        status_code=403,
        code="core.auth.account_disabled",
        title="Account disabled",
        detail="This account has been disabled.",
    )


async def _resolve_pat(session: AsyncSession, credential: str) -> CurrentUser:
    token_hash = hash_pat(credential)
    result = await session.execute(select(ApiToken).where(ApiToken.token_hash == token_hash))
    token_row = result.scalar_one_or_none()
    if token_row is None:
        raise AppError(
            status_code=401,
            code="core.auth.invalid_token",
            title="Invalid token",
            detail="The access token is invalid.",
        )
    if token_row.revoked_at is not None:
        raise AppError(
            status_code=401,
            code="core.auth.token_revoked",
            title="Token revoked",
            detail="This token has been revoked.",
        )
    now = datetime.now(UTC)
    if token_row.expires_at is not None and token_row.expires_at < now:
        raise AppError(
            status_code=401,
            code="core.auth.token_expired",
            title="Token expired",
            detail="This token has expired.",
        )

    user = await session.get(User, token_row.user_id)
    if user is None or not user.is_active:
        raise _account_disabled_error()

    if (
        token_row.last_used_at is None
        or (now - token_row.last_used_at) >= PAT_LAST_USED_UPDATE_INTERVAL
    ):
        token_row.last_used_at = now

    return CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        auth_method="api_token",
        token_id=token_row.id,
    )


async def _resolve_access_token(session: AsyncSession, credential: str) -> CurrentUser:
    settings = get_settings()
    try:
        payload = decode_access_token(credential, secret=settings.jwt_secret.get_secret_value())
    except ExpiredAccessTokenError as exc:
        raise AppError(
            status_code=401,
            code="core.auth.token_expired",
            title="Token expired",
            detail="This token has expired.",
        ) from exc
    except InvalidAccessTokenError as exc:
        raise _invalid_token_error() from exc

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise _invalid_token_error() from exc

    user = await session.get(User, user_id)
    if user is None:
        raise _invalid_token_error()
    if not user.is_active:
        raise _account_disabled_error()

    return CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        auth_method="access_token",
        token_id=None,
    )


async def current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    if authorization is None:
        raise _missing_credentials_error()

    match = _BEARER_RE.match(authorization)
    if match is None:
        raise _malformed_credentials_error()

    credential = match.group(1)

    resolved = (
        await _resolve_pat(session, credential)
        if is_pat(credential)
        else await _resolve_access_token(session, credential)
    )

    request.state.user_id = resolved.id
    return resolved


async def require_admin(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    if not user.is_admin:
        raise AppError(
            status_code=403,
            code="core.auth.admin_required",
            title="Admin required",
            detail="This action requires administrator privileges.",
        )
    return user


async def optional_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser | None:
    if authorization is None:
        return None
    return await current_user(request, session, authorization)
