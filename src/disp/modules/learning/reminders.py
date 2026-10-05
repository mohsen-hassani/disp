"""§7/§20: `learning.daily_nudge` — reminds users who opted in and have an
in-progress course. Mirrors `plants/reminders.py`'s idiom: one global query
across every user, then a per-user settings read with a defensive fallback
to defaults rather than letting one hand-edited row abort the whole sweep.
"""

from collections import defaultdict
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.modules.learning.models import Course, PathItem
from disp.modules.learning.service.mastery import _study_preferences

if TYPE_CHECKING:
    from disp.core.platform import Platform

logger = structlog.get_logger(__name__)

NOTIFICATION_TYPE = "learning.study_reminder"
MAX_TITLES_IN_BODY = 5


async def notify_due(session: AsyncSession, platform: "Platform") -> int:
    stmt = (
        select(Course.user_id, Course.id, Course.title)
        .join(PathItem, PathItem.course_id == Course.id)
        .where(
            Course.status == "active",
            Course.deleted_at.is_(None),
            PathItem.status == "approved",
            PathItem.completion_status != "completed",
        )
        .distinct()
    )
    rows = (await session.execute(stmt)).all()

    by_user: dict[UUID, list[str]] = defaultdict(list)
    for user_id, _course_id, title in rows:
        if title not in by_user[user_id]:
            by_user[user_id].append(title)

    notified = 0
    for user_id, titles in by_user.items():
        prefs = await _study_preferences(session, platform.store, user_id)
        if not prefs.daily_study_reminder:
            continue
        shown = titles[:MAX_TITLES_IN_BODY]
        body = "In progress: " + ", ".join(shown)
        if len(titles) > MAX_TITLES_IN_BODY:
            body += f" and {len(titles) - MAX_TITLES_IN_BODY} more"
        await platform.notifier.send(
            user_id, NOTIFICATION_TYPE, "Time to study", body, url="/learning"
        )
        notified += 1

    return notified
