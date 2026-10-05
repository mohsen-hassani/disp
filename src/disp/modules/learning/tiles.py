"""§20: the `learning.next_up` dashboard tile.

MUST NOT call the LLM — the dashboard enforces a 3-second timeout and
substitutes a fallback tile on any exception, so a tile that summarised
progress with a model call would degrade to the fallback exactly when it
matters (§20's own explicit warning: "a tempting tile").
"""

from uuid import UUID

from sqlalchemy import func, select

from disp.core.auth import readable_ids
from disp.core.contract import TileContext, TileData, TileItem
from disp.modules.learning.models import Course, PathItem, Topic, TopicTag, TopicTagScore
from disp.modules.learning.service.courses import RESOURCE_TYPE

TILE_ITEMS_LIMIT = 3
WEAKEST_TAGS_LIMIT = 2


async def learning_next_up_tile(ctx: TileContext) -> TileData:
    empty = TileData(
        key="learning.next_up",
        title="Learning",
        count=0,
        items=[],
        empty_text="No active courses",
        generated_at=ctx.now,
    )

    course_ids_raw = await readable_ids(
        ctx.session, user_id=ctx.user.id, resource_type=RESOURCE_TYPE
    )
    if not course_ids_raw:
        return empty
    course_ids = [UUID(cid) for cid in course_ids_raw]

    active_courses = list(
        (
            await ctx.session.execute(
                select(Course)
                .where(
                    Course.id.in_(course_ids),
                    Course.status == "active",
                    Course.deleted_at.is_(None),
                )
                .order_by(Course.created_at)
            )
        ).scalars()
    )
    if not active_courses:
        return empty

    active_course_ids = [c.id for c in active_courses]
    total_uncompleted = await ctx.session.scalar(
        select(func.count())
        .select_from(PathItem)
        .where(
            PathItem.course_id.in_(active_course_ids),
            PathItem.status == "approved",
            PathItem.completion_status != "completed",
        )
    )

    items: list[TileItem] = []
    for course in active_courses[:TILE_ITEMS_LIMIT]:
        next_item = (
            await ctx.session.execute(
                select(PathItem)
                .where(
                    PathItem.course_id == course.id,
                    PathItem.status == "approved",
                    PathItem.completion_status != "completed",
                )
                .order_by(PathItem.order_index)
                .limit(1)
            )
        ).scalar_one_or_none()
        if next_item is not None:
            items.append(
                TileItem(
                    id=str(next_item.id),
                    primary=next_item.title,
                    secondary=course.title,
                    href=f"/learning/{course.id}/items/{next_item.id}",
                )
            )

    weakest = (
        await ctx.session.execute(
            select(TopicTagScore, TopicTag, Topic.course_id)
            .join(TopicTag, TopicTag.id == TopicTagScore.topic_tag_id)
            .join(Topic, Topic.id == TopicTag.topic_id)
            .where(
                TopicTagScore.user_id == ctx.user.id,
                TopicTagScore.attempts_count > 0,
                Topic.course_id.in_(active_course_ids),
            )
            .order_by(TopicTagScore.rolling_score.asc())
            .limit(WEAKEST_TAGS_LIMIT)
        )
    ).all()
    for score, tag, course_id in weakest:
        items.append(
            TileItem(
                id=str(tag.id),
                primary=tag.name,
                secondary=f"{score.rolling_score:.0%} mastery",
                href=f"/learning/{course_id}",
            )
        )

    return TileData(
        key="learning.next_up",
        title="Learning",
        count=total_uncompleted or 0,
        items=items,
        empty_text="No active courses",
        generated_at=ctx.now,
    )
