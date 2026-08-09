import time
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from limits import RateLimitItemPerHour, RateLimitItemPerMinute
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth.dependencies import CurrentUser, current_user, require_admin
from disp.core.auth.invites import (
    InviteAlreadyAcceptedError,
    InviteExpiredError,
    InviteNotFoundError,
    InvitePendingError,
    UserAlreadyExistsError,
    accept_invite,
    create_invite,
    delete_pending_invite,
    list_pending_invites,
)
from disp.core.auth.passwords import (
    DUMMY_HASH,
    PasswordPolicyError,
    hash_password,
    validate_password_policy,
    verify_password,
)
from disp.core.auth.schemas import (
    AcceptInviteRequest,
    ApiTokenOut,
    CreateApiTokenRequest,
    CreateApiTokenResponse,
    CreateInviteRequest,
    CreateInviteResponse,
    InviteOut,
    LoginRequest,
    LoginResponse,
    MeResponse,
    PasswordChangeRequest,
    UserOut,
)
from disp.core.auth.sessions import (
    RefreshTokenExpiredError,
    RefreshTokenNotFoundError,
    RefreshTokenReusedError,
    SessionAccountDisabledError,
    create_session,
    revoke_all_for_user,
    revoke_family,
    rotate_refresh_token,
)
from disp.core.auth.tokens import (
    create_access_token,
    generate_pat,
    hash_pat,
    hash_refresh_token,
    pat_prefix,
)
from disp.core.config import Settings, get_settings
from disp.core.db import get_session
from disp.core.errors import AppError, limiter, problem_response
from disp.core.events import RefreshTokenReused as RefreshTokenReusedEvent
from disp.core.events import UserCreated, UserLoggedIn, publish_after_commit
from disp.core.models import ApiToken, Invite, User
from disp.core.models import Session as SessionModel

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["auth"])

REFRESH_COOKIE_NAME = "disp_refresh"
REFRESH_COOKIE_PATH = "/api/auth"
REQUIRED_CSRF_HEADER_VALUE = "disp"

_email_login_limiter = MovingWindowRateLimiter(MemoryStorage())
_EMAIL_LOGIN_RATE = RateLimitItemPerMinute(5)

_user_action_limiter = MovingWindowRateLimiter(MemoryStorage())
_TOKEN_CREATE_RATE = RateLimitItemPerHour(20)
_PASSWORD_CHANGE_RATE = RateLimitItemPerHour(5)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.refresh_token_ttl_seconds,
        domain=settings.cookie_domain,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        domain=settings.cookie_domain,
        samesite="lax",
        secure=settings.cookie_secure,
        httponly=True,
    )


def _error_response_clearing_cookie(
    request: Request,
    settings: Settings,
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
) -> JSONResponse:
    response = problem_response(
        request, status_code=status_code, code=code, title=title, detail=detail
    )
    _clear_refresh_cookie(response, settings)
    return response


def _invalid_credentials_error() -> AppError:
    return AppError(
        status_code=401,
        code="core.auth.invalid_credentials",
        title="Invalid credentials",
        detail="The email or password is incorrect.",
    )


def _account_disabled_error() -> AppError:
    return AppError(
        status_code=403,
        code="core.auth.account_disabled",
        title="Account disabled",
        detail="This account has been disabled.",
    )


def _require_csrf_header(x_requested_with: str | None) -> None:
    if x_requested_with != REQUIRED_CSRF_HEADER_VALUE:
        raise AppError(
            status_code=403,
            code="core.auth.csrf_required",
            title="CSRF header required",
            detail=f"The X-Requested-With: {REQUIRED_CSRF_HEADER_VALUE} header is required.",
        )


def _check_email_login_rate_limit(email: str) -> None:
    if not get_settings().rate_limit_enabled:
        return
    key = email.lower()
    if not _email_login_limiter.hit(_EMAIL_LOGIN_RATE, key):
        reset_time, _ = _email_login_limiter.get_window_stats(_EMAIL_LOGIN_RATE, key)
        retry_after = max(1, int(reset_time - time.time()))
        raise AppError(
            status_code=429,
            code="core.platform.rate_limited",
            title="Rate limited",
            detail="Too many login attempts for this email. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def _check_user_rate_limit(user_id: UUID, scope: str, item: RateLimitItemPerHour) -> None:
    if not get_settings().rate_limit_enabled:
        return
    key = f"{scope}:{user_id}"
    if not _user_action_limiter.hit(item, key):
        reset_time, _ = _user_action_limiter.get_window_stats(item, key)
        retry_after = max(1, int(reset_time - time.time()))
        raise AppError(
            status_code=429,
            code="core.platform.rate_limited",
            title="Rate limited",
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, email=user.email, display_name=user.display_name, is_admin=user.is_admin
    )


async def _issue_login_response(
    request: Request,
    response: Response,
    session: AsyncSession,
    settings: Settings,
    *,
    user: User,
    device_label: str | None,
) -> LoginResponse:
    issued = await create_session(
        session,
        user_id=user.id,
        ttl_seconds=settings.refresh_token_ttl_seconds,
        device_label=device_label,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        is_admin=user.is_admin,
        secret=settings.jwt_secret.get_secret_value(),
        ttl_seconds=settings.access_token_ttl_seconds,
    )
    publish_after_commit(
        session,
        UserLoggedIn(user_id=user.id, auth_method="access_token", ip_address=_client_ip(request)),
    )
    _set_refresh_cookie(response, issued.refresh_token, settings)
    return LoginResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_seconds,
        user=_user_out(user),
    )


# --------------------------------------------------------------------------
# Login / refresh / logout
# --------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=200,
    summary="Log in with email and password",
    operation_id="auth_login",
    responses={
        401: {"description": "Invalid credentials"},
        403: {"description": "Account disabled"},
        422: {"description": "Validation error"},
        429: {"description": "Rate limited"},
    },
)
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LoginResponse:
    settings = get_settings()
    _check_email_login_rate_limit(payload.email)

    result = await session.execute(
        select(User).where(func.lower(User.email) == payload.email.lower())
    )
    user = result.scalar_one_or_none()

    if user is None:
        verify_password(payload.password, DUMMY_HASH)
        raise _invalid_credentials_error()

    if not user.is_active:
        verify_password(payload.password, user.password_hash or DUMMY_HASH)
        raise _account_disabled_error()

    if user.password_hash is None:
        raise _invalid_credentials_error()

    if not verify_password(payload.password, user.password_hash):
        raise _invalid_credentials_error()

    return await _issue_login_response(
        request, response, session, settings, user=user, device_label=payload.device_label
    )


@router.post(
    "/refresh",
    response_model=LoginResponse,
    status_code=200,
    summary="Rotate the refresh token and issue a new access token",
    operation_id="auth_refresh",
    responses={
        401: {"description": "Invalid, expired, or reused refresh token"},
        403: {"description": "CSRF header missing, or account disabled"},
        429: {"description": "Rate limited"},
    },
)
@limiter.limit("60/minute")
async def refresh(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_requested_with: Annotated[str | None, Header()] = None,
) -> LoginResponse | JSONResponse:
    settings = get_settings()
    _require_csrf_header(x_requested_with)

    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if token is None:
        return _error_response_clearing_cookie(
            request,
            settings,
            status_code=401,
            code="core.auth.invalid_refresh_token",
            title="Invalid refresh token",
            detail="No refresh token was presented.",
        )

    try:
        outcome = await rotate_refresh_token(
            session,
            presented_token=token,
            ttl_seconds=settings.refresh_token_ttl_seconds,
            user_agent=request.headers.get("user-agent"),
            ip_address=_client_ip(request),
        )
    except RefreshTokenNotFoundError:
        return _error_response_clearing_cookie(
            request,
            settings,
            status_code=401,
            code="core.auth.invalid_refresh_token",
            title="Invalid refresh token",
            detail="The refresh token is unknown.",
        )
    except RefreshTokenReusedError as exc:
        logger.warning(
            "refresh_token_reused", user_id=str(exc.user_id), family_id=str(exc.family_id)
        )
        publish_after_commit(
            session, RefreshTokenReusedEvent(user_id=exc.user_id, family_id=exc.family_id)
        )
        return _error_response_clearing_cookie(
            request,
            settings,
            status_code=401,
            code="core.auth.refresh_token_reused",
            title="Refresh token reused",
            detail="This refresh token has already been used.",
        )
    except RefreshTokenExpiredError:
        return _error_response_clearing_cookie(
            request,
            settings,
            status_code=401,
            code="core.auth.refresh_token_expired",
            title="Refresh token expired",
            detail="This refresh token has expired.",
        )
    except SessionAccountDisabledError:
        return _error_response_clearing_cookie(
            request,
            settings,
            status_code=403,
            code="core.auth.account_disabled",
            title="Account disabled",
            detail="This account has been disabled.",
        )

    access_token = create_access_token(
        user_id=outcome.user.id,
        email=outcome.user.email,
        is_admin=outcome.user.is_admin,
        secret=settings.jwt_secret.get_secret_value(),
        ttl_seconds=settings.access_token_ttl_seconds,
    )
    _set_refresh_cookie(response, outcome.refresh_token, settings)
    return LoginResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_seconds,
        user=_user_out(outcome.user),
    )


@router.post(
    "/logout",
    status_code=204,
    summary="Revoke the current refresh token family",
    operation_id="auth_logout",
    responses={403: {"description": "CSRF header missing"}},
)
async def logout(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_requested_with: Annotated[str | None, Header()] = None,
) -> Response:
    settings = get_settings()
    _require_csrf_header(x_requested_with)

    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if token is not None:
        token_hash = hash_refresh_token(token)
        result = await session.execute(
            select(SessionModel.family_id).where(SessionModel.refresh_token_hash == token_hash)
        )
        family_id = result.scalar_one_or_none()
        if family_id is not None:
            await revoke_family(session, family_id=family_id, reason="logout")

    final_response = Response(status_code=204)
    _clear_refresh_cookie(final_response, settings)
    return final_response


# --------------------------------------------------------------------------
# Personal access tokens
# --------------------------------------------------------------------------


def _api_token_out(token: ApiToken) -> ApiTokenOut:
    return ApiTokenOut(
        id=token.id,
        name=token.name,
        token_prefix=token.token_prefix,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        expires_at=token.expires_at,
    )


@router.get(
    "/tokens",
    response_model=list[ApiTokenOut],
    status_code=200,
    summary="List the caller's personal access tokens",
    operation_id="auth_list_tokens",
)
async def list_tokens(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ApiTokenOut]:
    result = await session.execute(
        select(ApiToken)
        .where(ApiToken.user_id == user.id, ApiToken.revoked_at.is_(None))
        .order_by(ApiToken.created_at.desc())
    )
    return [_api_token_out(row) for row in result.scalars()]


@router.post(
    "/tokens",
    response_model=CreateApiTokenResponse,
    status_code=201,
    summary="Create a personal access token",
    operation_id="auth_create_token",
    responses={
        403: {"description": "PATs cannot mint further PATs"},
        429: {"description": "Rate limited"},
    },
)
async def create_token(
    request: Request,
    response: Response,
    payload: CreateApiTokenRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CreateApiTokenResponse:
    if user.auth_method == "api_token":
        raise AppError(
            status_code=403,
            code="core.auth.pat_cannot_mint",
            title="PATs cannot mint PATs",
            detail="A personal access token cannot be used to create another token.",
        )

    _check_user_rate_limit(user.id, "auth.tokens.create", _TOKEN_CREATE_RATE)

    plaintext = generate_pat()
    settings = get_settings()
    expires_at = None
    ttl_days = (
        payload.expires_in_days
        if payload.expires_in_days is not None
        else (settings.pat_default_ttl_days)
    )
    if ttl_days is not None:
        expires_at = datetime.now(UTC) + timedelta(days=ttl_days)

    row = ApiToken(
        user_id=user.id,
        name=payload.name,
        token_hash=hash_pat(plaintext),
        token_prefix=pat_prefix(plaintext),
        expires_at=expires_at,
    )
    session.add(row)
    await session.flush()

    response.headers["Location"] = f"/api/auth/tokens/{row.id}"
    return CreateApiTokenResponse(
        id=row.id,
        name=row.name,
        token_prefix=row.token_prefix,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        expires_at=row.expires_at,
        token=plaintext,
    )


@router.delete(
    "/tokens/{token_id}",
    status_code=204,
    summary="Revoke a personal access token",
    operation_id="auth_revoke_token",
    responses={404: {"description": "Token not found"}},
)
async def revoke_token(
    token_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    result = await session.execute(
        select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError(
            status_code=404,
            code="core.auth.token_not_found",
            title="Token not found",
            detail="The token does not exist.",
        )

    row.revoked_at = datetime.now(UTC)
    return Response(status_code=204)


# --------------------------------------------------------------------------
# Invites
# --------------------------------------------------------------------------


def _invite_out(invite: Invite) -> InviteOut:
    return InviteOut(
        id=invite.id,
        email=invite.email,
        is_admin=invite.is_admin,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
    )


@router.post(
    "/invites",
    response_model=CreateInviteResponse,
    status_code=201,
    summary="Invite a new user",
    operation_id="auth_create_invite",
    responses={
        403: {"description": "Admin required"},
        409: {"description": "User already exists or an invite is already pending"},
    },
)
async def create_invite_route(
    response: Response,
    payload: CreateInviteRequest,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CreateInviteResponse:
    settings = get_settings()
    try:
        invite, token = await create_invite(
            session,
            email=payload.email,
            is_admin=payload.is_admin,
            created_by=admin.id,
            ttl_seconds=settings.invite_ttl_seconds,
        )
    except UserAlreadyExistsError as exc:
        raise AppError(
            status_code=409,
            code="core.auth.user_exists",
            title="User already exists",
            detail="A user with this email address already exists.",
        ) from exc
    except InvitePendingError as exc:
        raise AppError(
            status_code=409,
            code="core.auth.invite_pending",
            title="Invite already pending",
            detail="A pending invite already exists for this email address.",
        ) from exc

    response.headers["Location"] = f"/api/auth/invites/{invite.id}"
    return CreateInviteResponse(
        id=invite.id,
        email=invite.email,
        token=token,
        accept_url=f"{settings.base_url}/accept-invite?token={token}",
        expires_at=invite.expires_at,
    )


@router.get(
    "/invites",
    response_model=list[InviteOut],
    status_code=200,
    summary="List pending invites",
    operation_id="auth_list_invites",
    responses={403: {"description": "Admin required"}},
)
async def list_invites_route(
    admin: Annotated[CurrentUser, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[InviteOut]:
    invites = await list_pending_invites(session)
    return [_invite_out(invite) for invite in invites]


@router.delete(
    "/invites/{invite_id}",
    status_code=204,
    summary="Cancel a pending invite",
    operation_id="auth_delete_invite",
    responses={
        403: {"description": "Admin required"},
        404: {"description": "Invite not found"},
    },
)
async def delete_invite_route(
    invite_id: UUID,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    deleted = await delete_pending_invite(session, invite_id)
    if not deleted:
        raise AppError(
            status_code=404,
            code="core.auth.invite_not_found",
            title="Invite not found",
            detail="The invite does not exist or has already been accepted.",
        )
    return Response(status_code=204)


@router.post(
    "/accept-invite",
    response_model=LoginResponse,
    status_code=201,
    summary="Accept an invite and create an account",
    operation_id="auth_accept_invite",
    responses={
        404: {"description": "Invite not found"},
        409: {"description": "Invite already used, or user already exists"},
        410: {"description": "Invite expired"},
        422: {"description": "Password policy violation"},
        429: {"description": "Rate limited"},
    },
)
@limiter.limit("10/hour")
async def accept_invite_route(
    request: Request,
    response: Response,
    payload: AcceptInviteRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LoginResponse:
    settings = get_settings()
    try:
        user = await accept_invite(
            session,
            token=payload.token,
            display_name=payload.display_name,
            password=payload.password,
        )
    except InviteNotFoundError as exc:
        raise AppError(
            status_code=404,
            code="core.auth.invite_not_found",
            title="Invite not found",
            detail="The invite token is unknown.",
        ) from exc
    except InviteAlreadyAcceptedError as exc:
        raise AppError(
            status_code=409,
            code="core.auth.invite_used",
            title="Invite already used",
            detail="This invite has already been accepted.",
        ) from exc
    except InviteExpiredError as exc:
        raise AppError(
            status_code=410,
            code="core.auth.invite_expired",
            title="Invite expired",
            detail="This invite has expired.",
        ) from exc
    except PasswordPolicyError as exc:
        raise AppError(
            status_code=422,
            code="core.auth.password_policy",
            title="Password policy violation",
            detail=exc.reason,
        ) from exc
    except UserAlreadyExistsError as exc:
        raise AppError(
            status_code=409,
            code="core.auth.user_exists",
            title="User already exists",
            detail="A user with this email address already exists.",
        ) from exc

    publish_after_commit(session, UserCreated(user_id=user.id, email=user.email))
    return await _issue_login_response(
        request, response, session, settings, user=user, device_label=None
    )


# --------------------------------------------------------------------------
# Password change / current user
# --------------------------------------------------------------------------


@router.post(
    "/password",
    status_code=204,
    summary="Change the caller's password",
    operation_id="auth_change_password",
    responses={
        401: {"description": "Current password incorrect"},
        403: {"description": "PATs may not change the password"},
        422: {"description": "Password policy violation"},
        429: {"description": "Rate limited"},
    },
)
async def change_password(
    request: Request,
    payload: PasswordChangeRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    if user.auth_method == "api_token":
        raise AppError(
            status_code=403,
            code="core.auth.pat_insufficient",
            title="PAT insufficient",
            detail="Personal access tokens cannot change the account password.",
        )

    _check_user_rate_limit(user.id, "auth.password.change", _PASSWORD_CHANGE_RATE)

    row = await session.get(User, user.id)
    if (
        row is None
        or row.password_hash is None
        or not verify_password(payload.current_password, row.password_hash)
    ):
        raise AppError(
            status_code=401,
            code="core.auth.invalid_credentials",
            title="Invalid credentials",
            detail="The current password is incorrect.",
        )

    try:
        validate_password_policy(payload.new_password, email=row.email)
    except PasswordPolicyError as exc:
        raise AppError(
            status_code=422,
            code="core.auth.password_policy",
            title="Password policy violation",
            detail=exc.reason,
        ) from exc

    row.password_hash = hash_password(payload.new_password)

    except_family_id = None
    cookie_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if cookie_token is not None:
        token_hash = hash_refresh_token(cookie_token)
        result = await session.execute(
            select(SessionModel.family_id).where(SessionModel.refresh_token_hash == token_hash)
        )
        except_family_id = result.scalar_one_or_none()

    await revoke_all_for_user(
        session,
        user_id=user.id,
        except_family_id=except_family_id,
        reason="password_change",
    )

    return Response(status_code=204)


@router.get(
    "/me",
    response_model=MeResponse,
    status_code=200,
    summary="Get the caller's identity",
    operation_id="auth_me",
)
async def me(user: Annotated[CurrentUser, Depends(current_user)]) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        auth_method=user.auth_method,
    )
