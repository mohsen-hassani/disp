from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth.tokens import generate_refresh_token, hash_refresh_token
from disp.core.models import Session as SessionModel
from disp.core.models import User

USER_AGENT_MAX_LEN = 256


class SessionError(Exception):
    pass


class RefreshTokenNotFoundError(SessionError):
    pass


class RefreshTokenReusedError(SessionError):
    def __init__(self, *, user_id: UUID, family_id: UUID) -> None:
        super().__init__("refresh token reused")
        self.user_id = user_id
        self.family_id = family_id


class RefreshTokenExpiredError(SessionError):
    pass


class SessionAccountDisabledError(SessionError):
    pass


@dataclass(frozen=True, slots=True)
class SessionIssued:
    session: SessionModel
    refresh_token: str


@dataclass(frozen=True, slots=True)
class RefreshOutcome:
    session: SessionModel
    refresh_token: str
    user: User


def _truncate_user_agent(user_agent: str | None) -> str | None:
    if user_agent is None:
        return None
    return user_agent[:USER_AGENT_MAX_LEN]


async def create_session(
    db: AsyncSession,
    *,
    user_id: UUID,
    ttl_seconds: int,
    device_label: str | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
    family_id: UUID | None = None,
    previous_session_id: UUID | None = None,
) -> SessionIssued:
    token = generate_refresh_token()
    row = SessionModel(
        user_id=user_id,
        family_id=family_id or uuid4(),
        refresh_token_hash=hash_refresh_token(token),
        previous_session_id=previous_session_id,
        device_label=device_label,
        user_agent=_truncate_user_agent(user_agent),
        ip_address=ip_address,
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )
    db.add(row)
    await db.flush()
    return SessionIssued(session=row, refresh_token=token)


async def rotate_refresh_token(
    db: AsyncSession,
    *,
    presented_token: str,
    ttl_seconds: int,
    user_agent: str | None,
    ip_address: str | None,
) -> RefreshOutcome:
    token_hash = hash_refresh_token(presented_token)
    stmt = (
        select(SessionModel).where(SessionModel.refresh_token_hash == token_hash).with_for_update()
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise RefreshTokenNotFoundError

    if row.revoked_at is not None or row.rotated_at is not None:
        await revoke_family(db, family_id=row.family_id, reason="reuse_detected")
        raise RefreshTokenReusedError(user_id=row.user_id, family_id=row.family_id)

    now = datetime.now(UTC)
    if row.expires_at < now:
        row.revoked_at = now
        row.revoked_reason = "expired"
        raise RefreshTokenExpiredError

    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise SessionAccountDisabledError

    new_token = generate_refresh_token()
    new_row = SessionModel(
        user_id=row.user_id,
        family_id=row.family_id,
        refresh_token_hash=hash_refresh_token(new_token),
        previous_session_id=row.id,
        device_label=row.device_label,
        user_agent=_truncate_user_agent(user_agent) or row.user_agent,
        ip_address=ip_address or row.ip_address,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    db.add(new_row)

    row.rotated_at = now
    row.revoked_at = now
    row.revoked_reason = "rotation"

    await db.flush()
    return RefreshOutcome(session=new_row, refresh_token=new_token, user=user)


async def revoke_family(db: AsyncSession, *, family_id: UUID, reason: str) -> None:
    now = datetime.now(UTC)
    stmt = (
        update(SessionModel)
        .where(SessionModel.family_id == family_id, SessionModel.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason=reason)
    )
    await db.execute(stmt)


async def revoke_all_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    except_family_id: UUID | None,
    reason: str,
) -> None:
    now = datetime.now(UTC)
    conditions = [SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None)]
    if except_family_id is not None:
        conditions.append(SessionModel.family_id != except_family_id)
    stmt = update(SessionModel).where(*conditions).values(revoked_at=now, revoked_reason=reason)
    await db.execute(stmt)
