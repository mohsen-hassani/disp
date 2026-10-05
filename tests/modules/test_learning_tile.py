"""M20 §20 (Phase 8): the `learning.next_up` dashboard tile. Constructed
directly via `TileContext`, mirroring `test_plants.py`'s tile tests —
`platform` is a bare `SimpleNamespace()` since the tile never touches it
(it must not call the LLM, and reads settings nowhere)."""

from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser, Permission, grant
from disp.core.contract import TileContext
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
from disp.modules.learning.service.courses import RESOURCE_TYPE, create_course
from disp.modules.learning.tiles import learning_next_up_tile
from tests.factories import current_user_for, make_user


async def _course(
    session: AsyncSession, email: str, *, status: str = "active"
) -> tuple[CurrentUser, Course]:
    user = await make_user(session, email=email)
    cu = current_user_for(user)
    course_out = await create_course(session, cu, CourseCreate(title="Design Patterns"))
    course = (await session.execute(select(Course).where(Course.id == course_out.id))).scalar_one()
    course.status = status
    await session.flush()
    return cu, course


def _ctx(user: CurrentUser, session: AsyncSession) -> TileContext:
    return TileContext(
        user=user,
        session=session,
        platform=SimpleNamespace(),  # type: ignore[arg-type]
        now=datetime.now(UTC),
    )


async def test_tile_is_empty_with_no_active_courses(db_session: AsyncSession) -> None:
    cu, _draft_course = await _course(db_session, "learning-tile-empty@example.com", status="draft")
    tile = await learning_next_up_tile(_ctx(cu, db_session))
    assert tile.count == 0
    assert tile.items == []
    assert tile.empty_text == "No active courses"


async def test_tile_counts_uncompleted_approved_items_and_lists_next_item(
    db_session: AsyncSession,
) -> None:
    cu, course = await _course(db_session, "learning-tile-count@example.com")
    first = PathItem(
        course_id=course.id, tier="beginner", order_index=0, title="First", status="approved"
    )
    second = PathItem(
        course_id=course.id, tier="beginner", order_index=1, title="Second", status="approved"
    )
    db_session.add_all([first, second])
    await db_session.flush()

    tile = await learning_next_up_tile(_ctx(cu, db_session))
    assert tile.count == 2
    assert tile.items[0].id == str(first.id)
    assert tile.items[0].primary == "First"
    assert tile.items[0].href == f"/learning/{course.id}/items/{first.id}"


async def test_tile_includes_weakest_tags(db_session: AsyncSession) -> None:
    cu, course = await _course(db_session, "learning-tile-weakest@example.com")
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
    item = PathItem(
        course_id=course.id, tier="beginner", order_index=0, title="Lesson", status="approved"
    )
    db_session.add(item)
    await db_session.flush()
    db_session.add(PathItemTopic(path_item_id=item.id, topic_id=topic.id))

    weak_tag = TopicTag(topic_id=topic.id, name="weak skill")
    db_session.add(weak_tag)
    await db_session.flush()
    db_session.add(
        TopicTagScore(topic_tag_id=weak_tag.id, user_id=cu.id, rolling_score=0.1, attempts_count=2)
    )
    await db_session.flush()

    tile = await learning_next_up_tile(_ctx(cu, db_session))
    tag_items = [i for i in tile.items if i.id == str(weak_tag.id)]
    assert len(tag_items) == 1
    assert tag_items[0].primary == "weak skill"


async def test_tile_excludes_courses_the_user_cannot_read(db_session: AsyncSession) -> None:
    await _course(db_session, "learning-tile-owner@example.com")
    stranger = await make_user(db_session, email="learning-tile-stranger@example.com")
    tile = await learning_next_up_tile(_ctx(current_user_for(stranger), db_session))
    assert tile.count == 0
    assert tile.empty_text == "No active courses"


async def test_tile_includes_shared_courses(db_session: AsyncSession) -> None:
    cu, course = await _course(db_session, "learning-tile-shared-owner@example.com")
    grantee = await make_user(db_session, email="learning-tile-shared-grantee@example.com")
    await grant(
        db_session,
        resource_type=RESOURCE_TYPE,
        resource_id=str(course.id),
        user_id=grantee.id,
        permission=Permission.READ,
        granted_by=cu.id,
    )
    item = PathItem(
        course_id=course.id, tier="beginner", order_index=0, title="Lesson", status="approved"
    )
    db_session.add(item)
    await db_session.flush()

    tile = await learning_next_up_tile(_ctx(current_user_for(grantee), db_session))
    assert tile.count == 1
