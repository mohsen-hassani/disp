"""M20 §9 (Phase 4): learning path generation, draft editing, approval.

Everything except `run_generate_path_job` takes an explicit session and
runs against the ordinary per-test-rollback `db_session`. `run_generate_path_job`
opens its own `session_scope()` (same shape as `run_index_job`, §16.2) and
needs the real-commit `real_db` fixture for the same reason
`test_learning_indexing.py` does — see that file's module docstring.
"""

import os
from collections.abc import AsyncIterator
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import Permission, grant
from disp.core.db import create_engine, create_session_maker
from disp.core.errors import AppError
from disp.core.llm import FakeLLM
from disp.modules.learning.llm_schemas import LearningPathDraft, PathItemDraft
from disp.modules.learning.models import (
    Course,
    Job,
    PathItem,
    PathItemTopic,
    Source,
    SourceSection,
    Topic,
    TopicSourceSection,
)
from disp.modules.learning.schemas import CourseCreate, PathItemUpdate
from disp.modules.learning.service.courses import create_course
from disp.modules.learning.service.path import (
    approve_path,
    create_generate_path_job,
    delete_path_item,
    get_path,
    get_path_item_content,
    run_generate_path_job,
    update_path_item,
)
from tests.factories import current_user_for, make_user


def _platform(llm: FakeLLM) -> SimpleNamespace:
    return SimpleNamespace(llm=llm)


@pytest.fixture
async def real_db() -> AsyncIterator[AsyncSession]:
    engine = create_engine(os.environ["DISP_DATABASE_URL"])
    maker = create_session_maker(engine)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _indexed_course(session: AsyncSession, email: str) -> tuple[object, Course, Topic]:
    """A course with one topic, standing in for "already indexed" — Phase 4
    doesn't need a real index run, just a topic to generate a path from."""
    user = await make_user(session, email=email)
    cu = current_user_for(user)
    course_out = await create_course(session, cu, CourseCreate(title="Design Patterns"))
    course = (await session.execute(select(Course).where(Course.id == course_out.id))).scalar_one()
    topic = Topic(course_id=course.id, canonical_name="Singleton pattern", description="d")
    session.add(topic)
    await session.flush()
    return cu, course, topic


async def test_create_generate_path_job_requires_indexed_course(db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="learning-path-noindex@example.com")
    cu = current_user_for(user)
    course = await create_course(db_session, cu, CourseCreate(title="Empty"))

    with pytest.raises(AppError) as exc_info:
        await create_generate_path_job(db_session, cu, course.id)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "modules.learning.not_indexed"


async def test_create_generate_path_job_conflicts_when_approved_path_exists(
    db_session: AsyncSession,
) -> None:
    cu, course, _topic = await _indexed_course(db_session, "learning-path-approved@example.com")
    item = PathItem(
        course_id=course.id, tier="beginner", order_index=0, title="Lesson", status="approved"
    )
    db_session.add(item)
    await db_session.flush()

    with pytest.raises(AppError) as exc_info:
        await create_generate_path_job(db_session, cu, course.id)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "modules.learning.path_already_approved"


async def test_create_generate_path_job_succeeds_and_double_create_conflicts(
    db_session: AsyncSession,
) -> None:
    cu, course, _topic = await _indexed_course(db_session, "learning-path-create@example.com")

    job_out, task_name = await create_generate_path_job(db_session, cu, course.id)
    await db_session.flush()
    assert task_name == "learning.generate_path"
    assert job_out.status == "queued"

    with pytest.raises(AppError) as exc_info:
        await create_generate_path_job(db_session, cu, course.id)
    assert exc_info.value.code == "modules.learning.job_already_running"


async def test_run_generate_path_job_writes_draft_items_dropping_invalid_topic_ids(
    real_db: AsyncSession,
) -> None:
    _cu, course, topic = await _indexed_course(real_db, "learning-path-run@example.com")
    course_id, user_id, topic_id = course.id, course.user_id, topic.id
    await real_db.commit()

    job = Job(course_id=course_id, user_id=user_id, kind="generate_path")
    real_db.add(job)
    await real_db.commit()
    job_id = job.id

    fake_llm = FakeLLM()
    fake_llm.register(
        "learning.generate_path",
        LearningPathDraft(
            items=[
                PathItemDraft(
                    title="Intro to Singletons",
                    tier="beginner",
                    topic_ids=[topic_id, UUID(int=0)],  # the second id doesn't resolve
                    est_minutes=30,
                )
            ]
        ),
    )

    await run_generate_path_job(_platform(fake_llm), job_id)  # type: ignore[arg-type]

    real_db.expire_all()
    refreshed_job = (await real_db.execute(select(Job).where(Job.id == job_id))).scalar_one()
    assert refreshed_job.status == "succeeded"

    items = list(
        (await real_db.execute(select(PathItem).where(PathItem.course_id == course_id))).scalars()
    )
    assert len(items) == 1
    assert items[0].title == "Intro to Singletons"
    assert items[0].status == "draft"

    topic_ids = list(
        (
            await real_db.execute(
                select(PathItemTopic.topic_id).where(PathItemTopic.path_item_id == items[0].id)
            )
        ).scalars()
    )
    assert topic_ids == [topic_id]  # the unresolved id was dropped, not inserted


async def test_get_path_returns_items_in_order(db_session: AsyncSession) -> None:
    cu, course, _topic = await _indexed_course(db_session, "learning-path-order@example.com")
    second = PathItem(course_id=course.id, tier="beginner", order_index=1, title="Second")
    first = PathItem(course_id=course.id, tier="beginner", order_index=0, title="First")
    db_session.add_all([second, first])
    await db_session.flush()

    items = await get_path(db_session, cu, course.id)
    assert [i.title for i in items] == ["First", "Second"]


async def test_get_path_on_unreadable_course_returns_404(db_session: AsyncSession) -> None:
    _cu, course, _topic = await _indexed_course(db_session, "learning-path-owner@example.com")
    stranger = await make_user(db_session, email="learning-path-stranger@example.com")

    with pytest.raises(AppError) as exc_info:
        await get_path(db_session, current_user_for(stranger), course.id)
    assert exc_info.value.status_code == 404


async def test_update_path_item_retitles_and_reassigns_topics(db_session: AsyncSession) -> None:
    cu, course, topic = await _indexed_course(db_session, "learning-path-update@example.com")
    other_topic = Topic(course_id=course.id, canonical_name="Other", description="d")
    db_session.add(other_topic)
    await db_session.flush()

    item = PathItem(course_id=course.id, tier="beginner", order_index=0, title="Original")
    db_session.add(item)
    await db_session.flush()
    db_session.add(PathItemTopic(path_item_id=item.id, topic_id=topic.id))
    await db_session.flush()

    updated = await update_path_item(
        db_session,
        cu,
        item.id,
        PathItemUpdate(title="Renamed", topic_ids=[other_topic.id, UUID(int=0)]),
    )
    assert updated.title == "Renamed"
    assert updated.topic_ids == [other_topic.id]  # the bogus id was dropped


async def test_update_path_item_forbidden_for_read_only_grantee(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="learning-path-ro-owner@example.com")
    reader = await make_user(db_session, email="learning-path-ro-reader@example.com")
    owner_cu = current_user_for(owner)
    course_out = await create_course(db_session, owner_cu, CourseCreate(title="Shared"))
    await grant(
        db_session,
        resource_type="learning.course",
        resource_id=str(course_out.id),
        user_id=reader.id,
        permission=Permission.READ,
        granted_by=owner.id,
    )
    item = PathItem(course_id=course_out.id, tier="beginner", order_index=0, title="Lesson")
    db_session.add(item)
    await db_session.flush()

    with pytest.raises(AppError) as exc_info:
        await update_path_item(
            db_session, current_user_for(reader), item.id, PathItemUpdate(title="Hacked")
        )
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "core.acl.forbidden"


async def test_delete_path_item_removes_row(db_session: AsyncSession) -> None:
    cu, course, _topic = await _indexed_course(db_session, "learning-path-delete@example.com")
    item = PathItem(course_id=course.id, tier="beginner", order_index=0, title="Lesson")
    db_session.add(item)
    await db_session.flush()
    item_id = item.id

    await delete_path_item(db_session, cu, item_id)
    await db_session.flush()

    remaining = (
        await db_session.execute(select(PathItem).where(PathItem.id == item_id))
    ).scalar_one_or_none()
    assert remaining is None


async def test_approve_path_flips_items_and_activates_course(db_session: AsyncSession) -> None:
    cu, course, _topic = await _indexed_course(db_session, "learning-path-approve@example.com")
    item = PathItem(course_id=course.id, tier="beginner", order_index=0, title="Lesson")
    db_session.add(item)
    await db_session.flush()

    approved = await approve_path(db_session, cu, course.id)
    assert approved[0].status == "approved"

    row = (await db_session.execute(select(Course).where(Course.id == course.id))).scalar_one()
    assert row.status == "active"


async def test_get_path_item_content_returns_joined_sections(db_session: AsyncSession) -> None:
    cu, course, topic = await _indexed_course(db_session, "learning-path-content@example.com")
    source = Source(course_id=course.id, title="Notes", content_type="markdown", raw_text="x")
    db_session.add(source)
    await db_session.flush()
    section = SourceSection(
        source_id=source.id,
        heading_path="Ch 1 > Singleton",
        order_index=0,
        content_text="A singleton restricts a class to one instance.",
    )
    db_session.add(section)
    await db_session.flush()
    db_session.add(TopicSourceSection(topic_id=topic.id, source_section_id=section.id))
    item = PathItem(course_id=course.id, tier="beginner", order_index=0, title="Lesson")
    db_session.add(item)
    await db_session.flush()
    db_session.add(PathItemTopic(path_item_id=item.id, topic_id=topic.id))
    await db_session.flush()

    content = await get_path_item_content(db_session, cu, item.id)
    assert len(content.sections) == 1
    assert content.sections[0].content_text == "A singleton restricts a class to one instance."
    assert content.path_item.id == item.id
