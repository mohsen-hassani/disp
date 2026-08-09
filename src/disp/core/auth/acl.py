from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.errors import AppError
from disp.core.models import Acl

if TYPE_CHECKING:
    from disp.core.auth.dependencies import CurrentUser


class Permission(StrEnum):
    READ = "read"
    WRITE = "write"
    OWNER = "owner"


_RANK: dict[Permission, int] = {
    Permission.READ: 1,
    Permission.WRITE: 2,
    Permission.OWNER: 3,
}

ACTION_REQUIRES: dict[str, Permission] = {
    "read": Permission.READ,
    "list": Permission.READ,
    "create": Permission.WRITE,
    "update": Permission.WRITE,
    "delete": Permission.WRITE,
    "share": Permission.OWNER,
    "unshare": Permission.OWNER,
    "transfer": Permission.OWNER,
}


@dataclass(frozen=True, slots=True)
class Grant:
    id: UUID
    resource_type: str
    resource_id: str
    user_id: UUID
    permission: Permission
    granted_by: UUID | None
    created_at: datetime


def _required_permission(action: str) -> Permission:
    try:
        return ACTION_REQUIRES[action]
    except KeyError as exc:
        raise ValueError(f"Unknown ACL action: {action!r}") from exc


async def can(
    session: AsyncSession,
    user: "CurrentUser",
    action: str,
    resource_type: str,
    resource_id: str | UUID,
) -> bool:
    required = _required_permission(action)
    stmt = select(Acl.permission).where(
        Acl.resource_type == resource_type,
        Acl.resource_id == str(resource_id),
        Acl.user_id == user.id,
    )
    result = await session.execute(stmt)
    row_permission = result.scalar_one_or_none()
    if row_permission is None:
        return False
    return _RANK[Permission(row_permission)] >= _RANK[required]


async def require(
    session: AsyncSession,
    user: "CurrentUser",
    action: str,
    resource_type: str,
    resource_id: str | UUID,
) -> None:
    if not await can(session, user, action, resource_type, resource_id):
        raise AppError(
            status_code=403,
            code="core.acl.forbidden",
            title="Forbidden",
            detail="You do not have permission to perform this action.",
        )


async def grant(
    session: AsyncSession,
    *,
    resource_type: str,
    resource_id: str | UUID,
    user_id: UUID,
    permission: Permission,
    granted_by: UUID,
) -> None:
    stmt = (
        pg_insert(Acl)
        .values(
            resource_type=resource_type,
            resource_id=str(resource_id),
            user_id=user_id,
            permission=permission.value,
            granted_by=granted_by,
        )
        .on_conflict_do_update(
            index_elements=[Acl.resource_type, Acl.resource_id, Acl.user_id],
            set_={"permission": permission.value, "granted_by": granted_by},
        )
    )
    await session.execute(stmt)


async def revoke(
    session: AsyncSession,
    *,
    resource_type: str,
    resource_id: str | UUID,
    user_id: UUID,
) -> None:
    stmt = sa_delete(Acl).where(
        Acl.resource_type == resource_type,
        Acl.resource_id == str(resource_id),
        Acl.user_id == user_id,
    )
    await session.execute(stmt)


async def list_grants(
    session: AsyncSession,
    *,
    resource_type: str,
    resource_id: str | UUID,
) -> list[Grant]:
    stmt = select(Acl).where(
        Acl.resource_type == resource_type,
        Acl.resource_id == str(resource_id),
    )
    result = await session.execute(stmt)
    return [
        Grant(
            id=row.id,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            user_id=row.user_id,
            permission=Permission(row.permission),
            granted_by=row.granted_by,
            created_at=row.created_at,
        )
        for row in result.scalars()
    ]


async def readable_ids(
    session: AsyncSession,
    *,
    user_id: UUID,
    resource_type: str,
) -> list[str]:
    stmt = select(Acl.resource_id).where(
        Acl.resource_type == resource_type,
        Acl.user_id == user_id,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
