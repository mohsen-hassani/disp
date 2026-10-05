"""M20 §15 (Phase 8): progress, weak points, and the two events mastery
updates and completion publish.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core import events as events_module
from disp.core.auth import CurrentUser
from disp.core.config import get_settings
from disp.core.events import EventBus, set_event_bus
from disp.core.settings_store import SettingsStore
from disp.modules.learning.events import MasteryUpdated
from disp.modules.learning.models import (
    Course,
    PathItem,
    PathItemTopic,
    Source,
    SourceSection,
    Topic,
    TopicSourceSection,
    TopicTag,
    TopicTagScore,
)
from disp.modules.learning.schemas import CourseCreate
from disp.modules.learning.service.courses import create_course
from disp.modules.learning.service.mastery import (
    get_progress,
    get_weak_points,
    record_observation,
)
from tests.factories import current_user_for, make_user


@pytest.fixture(autouse=True)
def _fresh_event_bus() -> Iterator[None]:
    previous = events_module._active_bus
    set_event_bus(EventBus())
    yield
    events_module._active_bus = previous


def _settings_store() -> SettingsStore:
    return SettingsStore(Fernet(get_settings().settings_key.get_secret_value()))


async def _course(session: AsyncSession, email: str) -> tuple[CurrentUser, Course]:
    user = await make_user(session, email=email)
    cu = current_user_for(user)
    course_out = await create_course(session, cu, CourseCreate(title="Design Patterns"))
    course = (await session.execute(select(Course).where(Course.id == course_out.id))).scalar_one()
    return cu, course


async def test_progress_counts_only_approved_items_and_buckets_by_tier(
    db_session: AsyncSession,
) -> None:
    cu, course = await _course(db_session, "learning-progress@example.com")
    done = PathItem(
        course_id=course.id,
        tier="beginner",
        order_index=0,
        title="Done",
        status="approved",
        completion_status="completed",
        completed_at=datetime.now(UTC),
    )
    pending = PathItem(
        course_id=course.id, tier="beginner", order_index=1, title="Pending", status="approved"
    )
    advanced_pending = PathItem(
        course_id=course.id, tier="advanced", order_index=2, title="Advanced", status="approved"
    )
    draft = PathItem(
        course_id=course.id, tier="beginner", order_index=3, title="Draft"
    )  # not approved
    db_session.add_all([done, pending, advanced_pending, draft])
    await db_session.flush()

    progress = await get_progress(db_session, cu, course.id)
    assert progress.completed == 1
    assert progress.total == 3  # draft excluded
    assert progress.by_tier["beginner"].total == 2
    assert progress.by_tier["beginner"].completed == 1
    assert progress.by_tier["advanced"].total == 1
    assert progress.by_tier["advanced"].completed == 0


async def test_weak_points_excludes_untested_tags_and_orders_ascending(
    db_session: AsyncSession,
) -> None:
    cu, course = await _course(db_session, "learning-weakpoints@example.com")
    source = Source(course_id=course.id, title="Notes", content_type="markdown", raw_text="x")
    db_session.add(source)
    await db_session.flush()
    section = SourceSection(
        source_id=source.id, heading_path="Ch 1", order_index=0, content_text="text"
    )
    db_session.add(section)
    await db_session.flush()

    topic = Topic(course_id=course.id, canonical_name="Singleton", description="d")
    db_session.add(topic)
    await db_session.flush()
    db_session.add(TopicSourceSection(topic_id=topic.id, source_section_id=section.id))

    weak_tag = TopicTag(topic_id=topic.id, name="weak skill")
    weaker_tag = TopicTag(topic_id=topic.id, name="weaker skill")
    untested_tag = TopicTag(topic_id=topic.id, name="untested skill")
    strong_tag = TopicTag(topic_id=topic.id, name="strong skill")
    db_session.add_all([weak_tag, weaker_tag, untested_tag, strong_tag])
    await db_session.flush()

    item = PathItem(
        course_id=course.id, tier="beginner", order_index=0, title="Lesson", status="approved"
    )
    db_session.add(item)
    await db_session.flush()
    db_session.add(PathItemTopic(path_item_id=item.id, topic_id=topic.id))

    db_session.add_all(
        [
            TopicTagScore(
                topic_tag_id=weak_tag.id, user_id=cu.id, rolling_score=0.4, attempts_count=1
            ),
            TopicTagScore(
                topic_tag_id=weaker_tag.id, user_id=cu.id, rolling_score=0.2, attempts_count=1
            ),
            TopicTagScore(
                topic_tag_id=untested_tag.id, user_id=cu.id, rolling_score=0.1, attempts_count=0
            ),  # excluded: never attempted
            TopicTagScore(
                topic_tag_id=strong_tag.id, user_id=cu.id, rolling_score=0.9, attempts_count=3
            ),  # excluded: above default 0.5 threshold
        ]
    )
    await db_session.flush()

    weak_points = await get_weak_points(db_session, cu, _settings_store(), course.id)
    assert [wp.tag_name for wp in weak_points] == ["weaker skill", "weak skill"]  # ascending
    assert weak_points[0].path_items[0].id == item.id


async def test_weak_point_threshold_is_read_from_the_users_settings(
    db_session: AsyncSession,
) -> None:
    cu, course = await _course(db_session, "learning-weakpoints-threshold@example.com")
    source = Source(course_id=course.id, title="Notes", content_type="markdown", raw_text="x")
    db_session.add(source)
    await db_session.flush()
    section = SourceSection(
        source_id=source.id, heading_path="Ch 1", order_index=0, content_text="text"
    )
    db_session.add(section)
    await db_session.flush()
    topic = Topic(course_id=course.id, canonical_name="Singleton", description="d")
    db_session.add(topic)
    await db_session.flush()
    db_session.add(TopicSourceSection(topic_id=topic.id, source_section_id=section.id))
    tag = TopicTag(topic_id=topic.id, name="borderline skill")
    db_session.add(tag)
    await db_session.flush()
    db_session.add(
        TopicTagScore(topic_tag_id=tag.id, user_id=cu.id, rolling_score=0.6, attempts_count=1)
    )
    await db_session.flush()

    store = _settings_store()
    # Default threshold (0.5) excludes a 0.6 score.
    assert await get_weak_points(db_session, cu, store, course.id) == []

    # Raising the threshold above 0.6 brings it into range.
    await store.set(
        db_session, user_id=cu.id, domain="learning", key="study.weak_point_threshold", value=0.7
    )
    await db_session.flush()
    weak_points = await get_weak_points(db_session, cu, store, course.id)
    assert len(weak_points) == 1


async def test_mastery_updated_event_carries_old_and_new_score(db_session: AsyncSession) -> None:
    cu, course = await _course(db_session, "learning-mastery-event@example.com")
    source = Source(course_id=course.id, title="Notes", content_type="markdown", raw_text="x")
    db_session.add(source)
    await db_session.flush()
    section = SourceSection(
        source_id=source.id, heading_path="Ch 1", order_index=0, content_text="text"
    )
    db_session.add(section)
    await db_session.flush()
    topic = Topic(course_id=course.id, canonical_name="Singleton", description="d")
    db_session.add(topic)
    await db_session.flush()
    db_session.add(TopicSourceSection(topic_id=topic.id, source_section_id=section.id))
    tag = TopicTag(topic_id=topic.id, name="a skill")
    db_session.add(tag)
    await db_session.flush()

    received: list[MasteryUpdated] = []
    events_module._active_bus.subscribe(MasteryUpdated, received.append)  # type: ignore[union-attr]

    await record_observation(db_session, topic_tag_id=tag.id, user_id=cu.id, observed=1.0)
    await db_session.commit()

    # publish_after_commit dispatches via a genuinely separate asyncio.Task
    # (core/events.py:_dispatch_pending) — it must be awaited explicitly,
    # the same pattern tests/core/test_events.py's own dispatch test uses.
    for task in list(events_module._background_tasks):
        await task

    assert len(received) == 1
    assert received[0].old_score == 1.0  # seeded: old == new on first observation
    assert received[0].new_score == 1.0
    assert received[0].course_id == course.id
