import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth.passwords import hash_password, validate_password_policy
from disp.core.models import Invite, User

INVITE_TOKEN_NBYTES = 32


class InviteError(Exception):
    pass


class UserAlreadyExistsError(InviteError):
    pass


class InvitePendingError(InviteError):
    pass


class InviteNotFoundError(InviteError):
    pass


class InviteAlreadyAcceptedError(InviteError):
    pass


class InviteExpiredError(InviteError):
    pass


def _hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _user_exists(db: AsyncSession, email: str) -> bool:
    result = await db.execute(select(User.id).where(func.lower(User.email) == email.lower()))
    return result.scalar_one_or_none() is not None


async def create_invite(
    db: AsyncSession,
    *,
    email: str,
    is_admin: bool,
    created_by: UUID,
    ttl_seconds: int,
) -> tuple[Invite, str]:
    if await _user_exists(db, email):
        raise UserAlreadyExistsError

    pending = await db.execute(
        select(Invite.id).where(
            func.lower(Invite.email) == email.lower(),
            Invite.accepted_at.is_(None),
        )
    )
    if pending.scalar_one_or_none() is not None:
        raise InvitePendingError

    token = secrets.token_urlsafe(INVITE_TOKEN_NBYTES)
    row = Invite(
        email=email,
        token_hash=_hash_invite_token(token),
        is_admin=is_admin,
        created_by=created_by,
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )
    db.add(row)
    await db.flush()
    return row, token


async def list_pending_invites(db: AsyncSession) -> list[Invite]:
    result = await db.execute(
        select(Invite).where(Invite.accepted_at.is_(None)).order_by(Invite.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_pending_invite(db: AsyncSession, invite_id: UUID) -> bool:
    result = await db.execute(
        select(Invite).where(Invite.id == invite_id, Invite.accepted_at.is_(None))
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await db.delete(row)
    return True


async def accept_invite(
    db: AsyncSession,
    *,
    token: str,
    display_name: str,
    password: str,
) -> User:
    token_hash = _hash_invite_token(token)
    result = await db.execute(select(Invite).where(Invite.token_hash == token_hash))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise InviteNotFoundError

    if invite.accepted_at is not None:
        raise InviteAlreadyAcceptedError

    if invite.expires_at < datetime.now(UTC):
        raise InviteExpiredError

    validate_password_policy(password, email=invite.email)

    if await _user_exists(db, invite.email):
        raise UserAlreadyExistsError

    user = User(
        email=invite.email,
        display_name=display_name,
        password_hash=hash_password(password),
        is_admin=invite.is_admin,
    )
    db.add(user)
    await db.flush()

    invite.accepted_at = datetime.now(UTC)
    invite.accepted_user_id = user.id

    return user
