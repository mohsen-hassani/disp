"""§15: mastery. `record_observation` (§15.1) was pulled forward to Phase 5
since quiz/exercise submission must write it in the same transaction as the
answer; progress (§15.2) and weak points (§15.3) land here with the
settings panel, which `weak_point_threshold` depends on.
"""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser
from disp.core.config import get_settings
from disp.core.events import publish_after_commit
from disp.core.settings_store import SettingsStore
from disp.modules.learning.config import get_learning_settings
from disp.modules.learning.events import MasteryUpdated
from disp.modules.learning.manifest import LearningSettingsSchema
from disp.modules.learning.models import PathItem, PathItemTopic, Topic, TopicTag, TopicTagScore
from disp.modules.learning.schemas import ProgressOut, TierProgress, WeakPointOut, WeakPointPathItem
from disp.modules.learning.service.courses import _authorize, _resolve_course


async def record_observation(
    session: AsyncSession, *, topic_tag_id: UUID, user_id: UUID, observed: float
) -> None:
    """`new = (1 - alpha) * old + alpha * observed`. A tag with no prior
    score is seeded AT `observed`, never at `alpha * observed` — a first
    perfect answer must not look like a weak 0.3 (§15.1). Caller's
    transaction owns the commit — this never commits itself, so it can run
    inside the same transaction as the answer/submission write.
    """
    course_id = await session.scalar(
        select(Topic.course_id)
        .join(TopicTag, TopicTag.topic_id == Topic.id)
        .where(TopicTag.id == topic_tag_id)
    )
    row = (
        await session.execute(
            select(TopicTagScore).where(
                TopicTagScore.topic_tag_id == topic_tag_id, TopicTagScore.user_id == user_id
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(ZoneInfo(get_settings().timezone))
    if row is None:
        session.add(
            TopicTagScore(
                topic_tag_id=topic_tag_id,
                user_id=user_id,
                rolling_score=observed,
                attempts_count=1,
                last_practiced_at=now,
            )
        )
        if course_id is not None:
            publish_after_commit(
                session,
                MasteryUpdated(
                    course_id=course_id,
                    user_id=user_id,
                    topic_tag_id=topic_tag_id,
                    old_score=observed,
                    new_score=observed,
                ),
            )
        return

    alpha = get_learning_settings().mastery_alpha
    old_score = row.rolling_score
    row.rolling_score = (1 - alpha) * row.rolling_score + alpha * observed
    row.attempts_count += 1
    row.last_practiced_at = now

    if course_id is not None:
        publish_after_commit(
            session,
            MasteryUpdated(
                course_id=course_id,
                user_id=user_id,
                topic_tag_id=topic_tag_id,
                old_score=old_score,
                new_score=row.rolling_score,
            ),
        )


async def _study_preferences(
    session: AsyncSession, store: SettingsStore, user_id: UUID
) -> LearningSettingsSchema:
    """`plants/reminders.py:_preferences()`'s idiom: read each field with the
    schema's own default, then a defensive re-validate that falls back to
    defaults rather than letting one hand-edited row break a read (§21)."""
    defaults = LearningSettingsSchema()
    daily_study_reminder = await store.get(
        session,
        user_id=user_id,
        domain="learning",
        key="study.daily_study_reminder",
        default=defaults.daily_study_reminder,
    )
    weak_point_threshold = await store.get(
        session,
        user_id=user_id,
        domain="learning",
        key="study.weak_point_threshold",
        default=defaults.weak_point_threshold,
    )
    try:
        return LearningSettingsSchema(
            daily_study_reminder=daily_study_reminder, weak_point_threshold=weak_point_threshold
        )
    except ValueError:
        return defaults


async def get_progress(session: AsyncSession, user: CurrentUser, course_id: UUID) -> ProgressOut:
    """§15.2: completed approved items over total approved items, plus a
    per-tier breakdown. Only quiz completion sets `completion_status`
    (§3.5), so counting it here already excludes exercise-only progress.
    Computed at read time, never stored (§3.8).
    """
    await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "read")

    stmt = select(PathItem.tier, PathItem.completion_status).where(
        PathItem.course_id == course_id, PathItem.status == "approved"
    )
    rows = (await session.execute(stmt)).all()

    by_tier: dict[str, TierProgress] = {}
    completed = 0
    for tier, completion_status in rows:
        entry = by_tier.setdefault(tier, TierProgress(total=0, completed=0))
        entry.total += 1
        if completion_status == "completed":
            entry.completed += 1
            completed += 1

    return ProgressOut(completed=completed, total=len(rows), by_tier=by_tier)


async def get_weak_points(
    session: AsyncSession, user: CurrentUser, store: SettingsStore, course_id: UUID
) -> list[WeakPointOut]:
    """§15.3: `topic_tag_score` rows below the user's `weak_point_threshold`,
    ascending, joined to their topic and to the approved path items that
    cover it. Tags with `attempts_count = 0` are excluded — an untested tag
    is unknown, not weak.
    """
    await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "read")
    prefs = await _study_preferences(session, store, user.id)

    stmt = (
        select(TopicTagScore, TopicTag, Topic)
        .join(TopicTag, TopicTag.id == TopicTagScore.topic_tag_id)
        .join(Topic, Topic.id == TopicTag.topic_id)
        .where(
            Topic.course_id == course_id,
            TopicTagScore.user_id == user.id,
            TopicTagScore.rolling_score < prefs.weak_point_threshold,
            TopicTagScore.attempts_count > 0,
        )
        .order_by(TopicTagScore.rolling_score.asc())
    )
    rows = (await session.execute(stmt)).all()

    results: list[WeakPointOut] = []
    for score, tag, topic in rows:
        covering = (
            await session.execute(
                select(PathItem.id, PathItem.title)
                .join(PathItemTopic, PathItemTopic.path_item_id == PathItem.id)
                .where(PathItemTopic.topic_id == topic.id, PathItem.status == "approved")
            )
        ).all()
        results.append(
            WeakPointOut(
                topic_tag_id=tag.id,
                tag_name=tag.name,
                topic_id=topic.id,
                topic_name=topic.canonical_name,
                rolling_score=score.rolling_score,
                path_items=[WeakPointPathItem(id=pid, title=title) for pid, title in covering],
            )
        )
    return results
