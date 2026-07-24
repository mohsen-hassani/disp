import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth.acl import Permission, can, grant, list_grants, readable_ids, require, revoke
from disp.core.errors import AppError
from tests.factories import current_user_for, make_user

RESOURCE_TYPE = "test.widget"


# Case 24: `can` honours the rank ladder (read < write < owner) for each action.


async def test_can_honours_rank_ladder(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="owner@example.com")
    reader = await make_user(db_session, email="reader@example.com")
    resource_id = "widget-1"

    await grant(
        db_session,
        resource_type=RESOURCE_TYPE,
        resource_id=resource_id,
        user_id=reader.id,
        permission=Permission.READ,
        granted_by=owner.id,
    )
    reader_cu = current_user_for(reader)

    assert await can(db_session, reader_cu, "read", RESOURCE_TYPE, resource_id) is True
    assert await can(db_session, reader_cu, "update", RESOURCE_TYPE, resource_id) is False
    assert await can(db_session, reader_cu, "share", RESOURCE_TYPE, resource_id) is False

    await grant(
        db_session,
        resource_type=RESOURCE_TYPE,
        resource_id=resource_id,
        user_id=reader.id,
        permission=Permission.WRITE,
        granted_by=owner.id,
    )
    assert await can(db_session, reader_cu, "read", RESOURCE_TYPE, resource_id) is True
    assert await can(db_session, reader_cu, "update", RESOURCE_TYPE, resource_id) is True
    assert await can(db_session, reader_cu, "share", RESOURCE_TYPE, resource_id) is False

    await grant(
        db_session,
        resource_type=RESOURCE_TYPE,
        resource_id=resource_id,
        user_id=reader.id,
        permission=Permission.OWNER,
        granted_by=owner.id,
    )
    assert await can(db_session, reader_cu, "share", RESOURCE_TYPE, resource_id) is True


# Case 25: absence of a grant denies.


async def test_absence_of_grant_denies(db_session: AsyncSession) -> None:
    stranger = await make_user(db_session, email="stranger@example.com")
    assert await can(db_session, current_user_for(stranger), "read", RESOURCE_TYPE, "nope") is False


# Case 26: `can` with an unknown action raises `ValueError`.


async def test_can_with_unknown_action_raises_value_error(db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="u@example.com")
    with pytest.raises(ValueError, match="Unknown ACL action"):
        await can(db_session, current_user_for(user), "obliterate", RESOURCE_TYPE, "x")


# Case 27: an admin has no implicit access to another user's resource.


async def test_admin_has_no_implicit_access(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="owner2@example.com")
    admin = await make_user(db_session, email="admin@example.com", is_admin=True)
    resource_id = "widget-2"

    await grant(
        db_session,
        resource_type=RESOURCE_TYPE,
        resource_id=resource_id,
        user_id=owner.id,
        permission=Permission.OWNER,
        granted_by=owner.id,
    )

    assert (
        await can(db_session, current_user_for(admin), "read", RESOURCE_TYPE, resource_id) is False
    )


# Case 28: `readable_ids` returns owned and shared ids and nothing else.


async def test_readable_ids_returns_owned_and_shared_only(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="owner3@example.com")
    other = await make_user(db_session, email="other3@example.com")

    await grant(
        db_session,
        resource_type=RESOURCE_TYPE,
        resource_id="owned-1",
        user_id=owner.id,
        permission=Permission.OWNER,
        granted_by=owner.id,
    )
    await grant(
        db_session,
        resource_type=RESOURCE_TYPE,
        resource_id="shared-1",
        user_id=owner.id,
        permission=Permission.READ,
        granted_by=other.id,
    )
    await grant(
        db_session,
        resource_type=RESOURCE_TYPE,
        resource_id="not-mine",
        user_id=other.id,
        permission=Permission.OWNER,
        granted_by=other.id,
    )

    ids = await readable_ids(db_session, user_id=owner.id, resource_type=RESOURCE_TYPE)
    assert set(ids) == {"owned-1", "shared-1"}


async def test_require_raises_app_error_when_denied(db_session: AsyncSession) -> None:
    stranger = await make_user(db_session, email="require-stranger@example.com")

    with pytest.raises(AppError) as exc_info:
        await require(db_session, current_user_for(stranger), "read", RESOURCE_TYPE, "nope")

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "acl.forbidden"


async def test_require_succeeds_when_permitted(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="require-owner@example.com")
    await grant(
        db_session,
        resource_type=RESOURCE_TYPE,
        resource_id="widget-req",
        user_id=owner.id,
        permission=Permission.READ,
        granted_by=owner.id,
    )

    await require(db_session, current_user_for(owner), "read", RESOURCE_TYPE, "widget-req")


async def test_revoke_removes_grant(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="revoke-owner@example.com")
    await grant(
        db_session,
        resource_type=RESOURCE_TYPE,
        resource_id="widget-revoke",
        user_id=owner.id,
        permission=Permission.OWNER,
        granted_by=owner.id,
    )

    await revoke(
        db_session, resource_type=RESOURCE_TYPE, resource_id="widget-revoke", user_id=owner.id
    )

    assert (
        await can(db_session, current_user_for(owner), "read", RESOURCE_TYPE, "widget-revoke")
        is False
    )


async def test_list_grants_returns_all_grants_for_a_resource(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="listgrants-owner@example.com")
    reader = await make_user(db_session, email="listgrants-reader@example.com")

    await grant(
        db_session,
        resource_type=RESOURCE_TYPE,
        resource_id="widget-list",
        user_id=owner.id,
        permission=Permission.OWNER,
        granted_by=owner.id,
    )
    await grant(
        db_session,
        resource_type=RESOURCE_TYPE,
        resource_id="widget-list",
        user_id=reader.id,
        permission=Permission.READ,
        granted_by=owner.id,
    )

    grants = await list_grants(db_session, resource_type=RESOURCE_TYPE, resource_id="widget-list")

    assert {g.user_id for g in grants} == {owner.id, reader.id}
    assert {g.permission for g in grants} == {Permission.OWNER, Permission.READ}
