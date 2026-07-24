from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser
from disp.core.auth.passwords import hash_password
from disp.core.auth.tokens import generate_pat, hash_pat, pat_prefix
from disp.core.models import ApiToken, Invite, User
from disp.core.models import Session as SessionModel

DEFAULT_PASSWORD = "a-perfectly-cromulent-password-123"  # noqa: S105


async def make_user(
    session: AsyncSession,
    *,
    email: str = "user@example.com",
    display_name: str = "Test User",
    password: str | None = DEFAULT_PASSWORD,
    is_admin: bool = False,
    is_active: bool = True,
) -> User:
    user = User(
        email=email,
        display_name=display_name,
        password_hash=hash_password(password) if password is not None else None,
        is_admin=is_admin,
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    return user


async def make_pat(
    session: AsyncSession,
    *,
    user_id: UUID,
    name: str = "test-token",
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
    last_used_at: datetime | None = None,
) -> tuple[ApiToken, str]:
    plaintext = generate_pat()
    row = ApiToken(
        user_id=user_id,
        name=name,
        token_hash=hash_pat(plaintext),
        token_prefix=pat_prefix(plaintext),
        expires_at=expires_at,
        revoked_at=revoked_at,
        last_used_at=last_used_at,
    )
    session.add(row)
    await session.flush()
    return row, plaintext


async def make_session_row(
    session: AsyncSession,
    *,
    user_id: UUID,
    refresh_token_hash: str,
    family_id: UUID | None = None,
    expires_at: datetime,
    revoked_at: datetime | None = None,
    revoked_reason: str | None = None,
    rotated_at: datetime | None = None,
) -> SessionModel:
    from uuid import uuid4

    row = SessionModel(
        user_id=user_id,
        family_id=family_id or uuid4(),
        refresh_token_hash=refresh_token_hash,
        expires_at=expires_at,
        revoked_at=revoked_at,
        revoked_reason=revoked_reason,
        rotated_at=rotated_at,
    )
    session.add(row)
    await session.flush()
    return row


async def make_invite(
    session: AsyncSession,
    *,
    email: str,
    is_admin: bool,
    created_by: UUID,
    expires_at: datetime,
    token_hash: str,
    accepted_at: datetime | None = None,
) -> Invite:
    row = Invite(
        email=email,
        token_hash=token_hash,
        is_admin=is_admin,
        created_by=created_by,
        expires_at=expires_at,
        accepted_at=accepted_at,
    )
    session.add(row)
    await session.flush()
    return row


def current_user_for(
    user: User, *, auth_method: str = "access_token", token_id: UUID | None = None
) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        auth_method=auth_method,  # type: ignore[arg-type]
        token_id=token_id,
    )
