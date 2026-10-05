"""Phase 1 (M20 §3): course CRUD only. `learning.course` is the aggregate
root and the ACL boundary (TECHNICAL-SPEC.md §19) — every later phase's
child entities inherit this grant rather than carrying their own, so the
resolve-then-authorize / 404-not-403 behaviour proven here is the pattern
every subsequent phase reuses.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import Permission, grant
from disp.core.config import get_settings
from disp.core.errors import AppError
from disp.core.files import FileStore
from disp.modules.learning.config import get_learning_settings
from disp.modules.learning.models import Course
from disp.modules.learning.schemas import CourseCreate, CourseUpdate
from disp.modules.learning.service.courses import (
    RESOURCE_TYPE,
    create_course,
    delete_course,
    get_course,
    list_courses,
    update_course,
)
from tests.factories import current_user_for, make_user


async def test_create_course_persists_and_grants_owner(db_session: AsyncSession) -> None:
    from disp.core.auth.acl import can

    user = await make_user(db_session, email="learning-create@example.com")
    cu = current_user_for(user)

    course = await create_course(db_session, cu, CourseCreate(title="Design Patterns"))
    await db_session.flush()

    row = (await db_session.execute(select(Course).where(Course.id == course.id))).scalar_one()
    assert row.title == "Design Patterns"
    assert row.status == "draft"
    assert row.user_id == user.id

    assert await can(db_session, cu, "read", RESOURCE_TYPE, str(course.id)) is True
    assert await can(db_session, cu, "share", RESOURCE_TYPE, str(course.id)) is True


async def test_list_excludes_deleted_and_other_users_courses(db_session: AsyncSession) -> None:
    from datetime import UTC, datetime

    owner = await make_user(db_session, email="learning-list-owner@example.com")
    other = await make_user(db_session, email="learning-list-other@example.com")
    owner_cu = current_user_for(owner)

    visible = await create_course(db_session, owner_cu, CourseCreate(title="Visible"))
    to_delete = await create_course(db_session, owner_cu, CourseCreate(title="To delete"))
    await create_course(db_session, current_user_for(other), CourseCreate(title="Not mine"))

    row = (await db_session.execute(select(Course).where(Course.id == to_delete.id))).scalar_one()
    row.deleted_at = datetime.now(UTC)
    await db_session.flush()

    page = await list_courses(db_session, owner_cu, limit=20, cursor=None)

    ids = {item.id for item in page.items}
    assert ids == {visible.id}


async def test_reading_another_users_course_returns_404(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="learning-404-owner@example.com")
    stranger = await make_user(db_session, email="learning-404-stranger@example.com")

    course = await create_course(db_session, current_user_for(owner), CourseCreate(title="Private"))

    with pytest.raises(AppError) as exc_info:
        await get_course(db_session, current_user_for(stranger), course.id)
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "modules.learning.not_found"


async def test_grant_read_permits_read_forbids_write(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="learning-share-owner@example.com")
    grantee = await make_user(db_session, email="learning-share-grantee@example.com")
    owner_cu = current_user_for(owner)

    course = await create_course(db_session, owner_cu, CourseCreate(title="Shared"))
    await grant(
        db_session,
        resource_type=RESOURCE_TYPE,
        resource_id=str(course.id),
        user_id=grantee.id,
        permission=Permission.READ,
        granted_by=owner.id,
    )

    grantee_cu = current_user_for(grantee)
    fetched = await get_course(db_session, grantee_cu, course.id)
    assert fetched.id == course.id

    with pytest.raises(AppError) as exc_info:
        await update_course(db_session, grantee_cu, course.id, CourseUpdate(title="Hacked"))
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "core.acl.forbidden"


async def test_update_course_changes_title_and_description(db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="learning-update@example.com")
    cu = current_user_for(user)
    course = await create_course(db_session, cu, CourseCreate(title="Original"))

    updated = await update_course(
        db_session, cu, course.id, CourseUpdate(title="Renamed", description="New description")
    )

    assert updated.title == "Renamed"
    assert updated.description == "New description"


async def test_delete_course_soft_deletes_then_not_found(db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="learning-delete@example.com")
    cu = current_user_for(user)
    course = await create_course(db_session, cu, CourseCreate(title="Temporary"))

    await delete_course(db_session, cu, course.id, files=FileStore.from_settings(get_settings()))
    await db_session.flush()

    with pytest.raises(AppError) as exc_info:
        await get_course(db_session, cu, course.id)
    assert exc_info.value.status_code == 404


async def test_pagination_stable_non_overlapping_across_pages(db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="learning-paginate@example.com")
    cu = current_user_for(user)

    created_ids = []
    for i in range(23):
        course = await create_course(db_session, cu, CourseCreate(title=f"Course {i}"))
        created_ids.append(course.id)

    seen: list = []
    cursor = None
    for _ in range(10):
        page = await list_courses(db_session, cu, limit=10, cursor=cursor)
        seen.extend(item.id for item in page.items)
        if not page.has_more:
            break
        cursor = page.next_cursor

    assert len(seen) == len(created_ids)
    assert set(seen) == set(created_ids)


async def test_learning_settings_defaults_match_spec() -> None:
    get_learning_settings.cache_clear()
    settings = get_learning_settings()
    assert settings.max_source_bytes == 10 * 1024 * 1024
    assert settings.max_sources_per_course == 25
    assert (settings.quiz_questions_min, settings.quiz_questions_max) == (5, 8)
    assert (settings.exercise_steps_min, settings.exercise_steps_max) == (3, 6)
    assert settings.target_item_minutes == 30
    assert settings.mastery_alpha == 0.3
    assert settings.alignment_similarity_threshold == 0.75
    assert settings.chat_history_messages == 20
    assert settings.chat_freeform_top_k == 8


async def test_learning_settings_env_prefix_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `get_learning_settings()` cache trap `plants/config.py` documents:
    a test that overrides an env var MUST call cache_clear() before AND
    after, or the override leaks into (or a stale value leaks out of) other
    tests via the process-wide lru_cache."""
    monkeypatch.setenv("DISP_LEARNING_MASTERY_ALPHA", "0.5")
    get_learning_settings.cache_clear()
    try:
        assert get_learning_settings().mastery_alpha == 0.5
    finally:
        get_learning_settings.cache_clear()
