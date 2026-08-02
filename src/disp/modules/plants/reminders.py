from collections import defaultdict
from datetime import date, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.config import get_settings
from disp.modules.plants import service
from disp.modules.plants.manifest import PlantsSettingsSchema
from disp.modules.plants.models import CareInterval, Plant
from disp.modules.plants.tiles import describe_lateness

if TYPE_CHECKING:
    from disp.core.platform import Platform

logger = structlog.get_logger(__name__)

NOTIFICATION_TYPE = "plants.care_due"
# The widest look-ahead any user can configure. One query covers everyone;
# each user's own (narrower) preference is applied in Python afterwards.
MAX_LOOKAHEAD_DAYS = 14
# Keep a push notification readable — the app has the full list.
MAX_BODY_LINES = 10


def _defaults() -> PlantsSettingsSchema:
    return PlantsSettingsSchema()


async def _preferences(
    session: AsyncSession, platform: "Platform", user_id: UUID
) -> PlantsSettingsSchema:
    defaults = _defaults()
    daily_push = await platform.store.get(
        session,
        user_id=user_id,
        domain="plants",
        key="reminders.daily_push",
        default=defaults.daily_push,
    )
    lookahead = await platform.store.get(
        session,
        user_id=user_id,
        domain="plants",
        key="reminders.include_upcoming_days",
        default=defaults.include_upcoming_days,
    )
    # A hand-edited settings row could hold anything; fall back rather than
    # letting one bad value abort the whole sweep.
    try:
        return PlantsSettingsSchema(daily_push=daily_push, include_upcoming_days=lookahead)
    except ValueError:
        logger.warning("plants_invalid_reminder_settings", user_id=str(user_id))
        return defaults


def _body(rows: list[tuple[str, str, int]]) -> str:
    lines = [
        f"• {action_name} — {plant_name} ({describe_lateness(days_overdue)})"
        for plant_name, action_name, days_overdue in rows[:MAX_BODY_LINES]
    ]
    if len(rows) > MAX_BODY_LINES:
        lines.append(f"…and {len(rows) - MAX_BODY_LINES} more")
    return "\n".join(lines)


async def notify_due(session: AsyncSession, platform: "Platform") -> int:
    """Send each user one digest of the plant care they owe.

    Runs as a single global sweep (this is a scheduled job, not a request),
    grouped by the plant's owner. Returns the number of users notified.
    """
    # Via the module rather than a direct name import, so `today` has exactly
    # one definition to stub when a test needs a fixed date.
    on_day = service.today()
    horizon = on_day + timedelta(days=MAX_LOOKAHEAD_DAYS)

    result = await session.execute(
        select(Plant.user_id, Plant.name, CareInterval.name, CareInterval.next_due_on)
        .join(CareInterval, CareInterval.plant_id == Plant.id)
        .where(
            Plant.deleted_at.is_(None),
            CareInterval.active.is_(True),
            CareInterval.next_due_on <= horizon,
        )
        .order_by(Plant.user_id, CareInterval.next_due_on, Plant.name, CareInterval.name)
    )

    by_user: dict[UUID, list[tuple[str, str, date]]] = defaultdict(list)
    for user_id, plant_name, action_name, next_due_on in result.all():
        by_user[user_id].append((plant_name, action_name, next_due_on))

    sent = 0
    for user_id, rows in by_user.items():
        prefs = await _preferences(session, platform, user_id)
        if not prefs.daily_push:
            continue

        cutoff = on_day + timedelta(days=prefs.include_upcoming_days)
        due = [
            (plant_name, action_name, (on_day - next_due_on).days)
            for plant_name, action_name, next_due_on in rows
            if next_due_on <= cutoff
        ]
        if not due:
            continue
        due.sort(key=lambda row: (-row[2], row[0], row[1]))

        overdue = [row for row in due if row[2] > 0]
        title = service.summarize(
            len(due), len(overdue), max((row[2] for row in overdue), default=0)
        )
        await platform.notifier.send(
            user_id,
            NOTIFICATION_TYPE,
            title,
            _body(due),
            url=f"{get_settings().base_url}/plants",
        )
        sent += 1

    return sent
