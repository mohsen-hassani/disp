import calendar as calendar_module
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from disp.core.auth import CurrentUser, Permission, can, grant, readable_ids
from disp.core.config import get_settings
from disp.core.errors import AppError
from disp.core.events import publish_after_commit
from disp.core.pagination import Page, decode_cursor, encode_cursor
from disp.modules.plants.config import get_plants_settings, sniff_image_type
from disp.modules.plants.events import CareCompleted, PlantCreated, PlantDeleted
from disp.modules.plants.models import CareInterval, CareLog, Plant
from disp.modules.plants.schemas import (
    CalendarEntry,
    CalendarOut,
    CareIntervalCreate,
    CareIntervalOut,
    CareIntervalUpdate,
    CareLogOut,
    CompleteRequest,
    CompleteResult,
    DueItem,
    DueSummary,
    PlantCreate,
    PlantDetailOut,
    PlantOut,
    PlantUpdate,
)
from disp.modules.plants.storage import absolute_path, remove_image, write_image

RESOURCE_TYPE = "plants.plant"

# How far back a completion may be back-dated. Long enough to cover "I forgot
# to log last month's repotting", short enough that a typo'd year is rejected.
MAX_BACKDATE_DAYS = 365
# Hard ceiling on one calendar response, so a pathological set of 1-day
# intervals can't generate an unbounded projection list.
MAX_CALENDAR_ENTRIES = 2000


def today() -> date:
    """Today in the deployment's configured timezone, not the server's UTC date.

    Every due/overdue comparison in this module goes through here: a
    reminder that flips over at UTC midnight would fire at the wrong local
    hour for anyone not on UTC.
    """
    return datetime.now(ZoneInfo(get_settings().timezone)).date()


def _not_found_error() -> AppError:
    return AppError(
        status_code=404,
        code="modules.plants.not_found",
        title="Plant not found",
        detail="The plant does not exist or is not visible to you.",
    )


def _interval_not_found_error() -> AppError:
    return AppError(
        status_code=404,
        code="modules.plants.interval_not_found",
        title="Care interval not found",
        detail="The care interval does not exist on this plant.",
    )


async def _resolve_plant(session: AsyncSession, plant_id: UUID) -> Plant:
    plant = await session.get(Plant, plant_id)
    if plant is None or plant.deleted_at is not None:
        raise _not_found_error()
    return plant


async def _authorize(session: AsyncSession, user: CurrentUser, plant_id: UUID, action: str) -> None:
    """Resolve-then-require with existence hidden for unreadable plants: a
    caller who can't read the plant gets 404, never 403. A caller who can read
    it but lacks the specific permission gets 403. Intervals and logs have no
    ACL rows of their own — they inherit the owning plant's."""
    if await can(session, user, action, RESOURCE_TYPE, str(plant_id)):
        return
    if action == "read" or not await can(session, user, "read", RESOURCE_TYPE, str(plant_id)):
        raise _not_found_error()
    raise AppError(
        status_code=403,
        code="core.acl.forbidden",
        title="Forbidden",
        detail="You do not have permission to perform this action.",
    )


async def _resolve_interval(
    session: AsyncSession, plant_id: UUID, interval_id: UUID
) -> CareInterval:
    interval = await session.get(CareInterval, interval_id)
    if interval is None or interval.plant_id != plant_id:
        raise _interval_not_found_error()
    return interval


# --------------------------------------------------------------------------
# Serialization
# --------------------------------------------------------------------------


def _days_overdue(next_due_on: date, on_day: date) -> int:
    """Positive = this many days behind, 0 = due today, negative = not yet due."""
    return (on_day - next_due_on).days


def _to_interval_out(interval: CareInterval, on_day: date) -> CareIntervalOut:
    return CareIntervalOut(
        id=interval.id,
        plant_id=interval.plant_id,
        name=interval.name,
        interval_days=interval.interval_days,
        next_due_on=interval.next_due_on,
        last_done_on=interval.last_done_on,
        active=interval.active,
        days_overdue=_days_overdue(interval.next_due_on, on_day),
        created_at=interval.created_at,
        updated_at=interval.updated_at,
    )


def _to_log_out(log: CareLog) -> CareLogOut:
    return CareLogOut(
        id=log.id,
        plant_id=log.plant_id,
        interval_id=log.interval_id,
        action_name=log.action_name,
        due_on=log.due_on,
        completed_on=log.completed_on,
        days_late=log.days_late,
        note=log.note,
        created_at=log.created_at,
    )


def _to_plant_out(plant: Plant, intervals: list[CareInterval], on_day: date) -> PlantOut:
    active = [i for i in intervals if i.active]
    overdue = [_days_overdue(i.next_due_on, on_day) for i in active]
    due = [d for d in overdue if d >= 0]
    return PlantOut(
        id=plant.id,
        name=plant.name,
        description=plant.description,
        care_notes=plant.care_notes,
        has_image=plant.image_path is not None,
        image_url=f"/api/plants/{plant.id}/image" if plant.image_path else None,
        due_count=len(due),
        max_days_overdue=max(due) if due else 0,
        next_due_on=min((i.next_due_on for i in active), default=None),
        created_at=plant.created_at,
        updated_at=plant.updated_at,
    )


async def _intervals_for(
    session: AsyncSession, plant_ids: list[UUID]
) -> dict[UUID, list[CareInterval]]:
    if not plant_ids:
        return {}
    result = await session.execute(
        select(CareInterval)
        .where(CareInterval.plant_id.in_(plant_ids))
        .order_by(CareInterval.next_due_on, CareInterval.name)
    )
    grouped: dict[UUID, list[CareInterval]] = {plant_id: [] for plant_id in plant_ids}
    for interval in result.scalars():
        grouped[interval.plant_id].append(interval)
    return grouped


# --------------------------------------------------------------------------
# Plants
# --------------------------------------------------------------------------


async def list_plants(
    session: AsyncSession,
    user: CurrentUser,
    *,
    limit: int,
    cursor: str | None,
    q: str | None,
) -> Page[PlantOut]:
    ids = await readable_ids(session, user_id=user.id, resource_type=RESOURCE_TYPE)
    if not ids:
        return Page[PlantOut](items=[], next_cursor=None, has_more=False)

    conditions: list[ColumnElement[bool]] = [
        Plant.id.in_([UUID(resource_id) for resource_id in ids]),
        Plant.deleted_at.is_(None),
    ]
    if q:
        conditions.append(Plant.name.ilike(f"%{q}%"))

    if cursor:
        cursor_data = decode_cursor(cursor)
        try:
            seek_id = UUID(cursor_data.id)
        except ValueError as exc:
            raise AppError(
                status_code=400,
                code="core.pagination.invalid_cursor",
                title="Invalid cursor",
                detail="The pagination cursor could not be decoded.",
            ) from exc
        conditions.append(
            tuple_(Plant.created_at, Plant.id) < tuple_(literal(cursor_data.ts), literal(seek_id))
        )

    result = await session.execute(
        select(Plant)
        .where(*conditions)
        .order_by(Plant.created_at.desc(), Plant.id.desc())
        .limit(limit + 1)
    )
    rows = list(result.scalars())

    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id)

    on_day = today()
    intervals = await _intervals_for(session, [row.id for row in rows])
    return Page[PlantOut](
        items=[_to_plant_out(row, intervals.get(row.id, []), on_day) for row in rows],
        next_cursor=next_cursor,
        has_more=has_more,
    )


async def get_plant(session: AsyncSession, user: CurrentUser, plant_id: UUID) -> PlantDetailOut:
    plant = await _resolve_plant(session, plant_id)
    await _authorize(session, user, plant_id, "read")

    on_day = today()
    intervals = (await _intervals_for(session, [plant_id])).get(plant_id, [])
    base = _to_plant_out(plant, intervals, on_day)
    return PlantDetailOut(
        **base.model_dump(),
        intervals=[_to_interval_out(interval, on_day) for interval in intervals],
    )


async def create_plant(session: AsyncSession, user: CurrentUser, payload: PlantCreate) -> PlantOut:
    plant = Plant(
        user_id=user.id,
        name=payload.name,
        description=payload.description,
        care_notes=payload.care_notes,
    )
    session.add(plant)
    await session.flush()

    await grant(
        session,
        resource_type=RESOURCE_TYPE,
        resource_id=str(plant.id),
        user_id=user.id,
        permission=Permission.OWNER,
        granted_by=user.id,
    )
    publish_after_commit(session, PlantCreated(plant_id=plant.id, user_id=user.id, name=plant.name))
    return _to_plant_out(plant, [], today())


async def update_plant(
    session: AsyncSession, user: CurrentUser, plant_id: UUID, payload: PlantUpdate
) -> PlantOut:
    plant = await _resolve_plant(session, plant_id)
    await _authorize(session, user, plant_id, "update")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plant, field, value)
    plant.updated_at = datetime.now(UTC)

    intervals = (await _intervals_for(session, [plant_id])).get(plant_id, [])
    return _to_plant_out(plant, intervals, today())


async def delete_plant(session: AsyncSession, user: CurrentUser, plant_id: UUID) -> None:
    plant = await _resolve_plant(session, plant_id)
    await _authorize(session, user, plant_id, "delete")

    now = datetime.now(UTC)
    plant.deleted_at = now
    plant.updated_at = now
    publish_after_commit(session, PlantDeleted(plant_id=plant.id, user_id=user.id))


# --------------------------------------------------------------------------
# Care intervals
# --------------------------------------------------------------------------


async def add_interval(
    session: AsyncSession, user: CurrentUser, plant_id: UUID, payload: CareIntervalCreate
) -> CareIntervalOut:
    await _resolve_plant(session, plant_id)
    await _authorize(session, user, plant_id, "update")

    on_day = today()
    last_done_on = payload.last_done_on if payload.last_done_on is not None else on_day
    if last_done_on > on_day:
        raise AppError(
            status_code=400,
            code="modules.plants.future_date",
            title="Date is in the future",
            detail="last_done_on cannot be in the future.",
        )

    interval = CareInterval(
        plant_id=plant_id,
        name=payload.name,
        interval_days=payload.interval_days,
        last_done_on=payload.last_done_on,
        next_due_on=last_done_on + timedelta(days=payload.interval_days),
    )
    session.add(interval)
    await session.flush()
    return _to_interval_out(interval, on_day)


async def update_interval(
    session: AsyncSession,
    user: CurrentUser,
    plant_id: UUID,
    interval_id: UUID,
    payload: CareIntervalUpdate,
) -> CareIntervalOut:
    await _resolve_plant(session, plant_id)
    await _authorize(session, user, plant_id, "update")
    interval = await _resolve_interval(session, plant_id, interval_id)

    # The point the current cycle started from. `last_done_on` is None until
    # the action has actually been completed once, so fall back to working it
    # backwards from the scheduled date under the *old* cadence — captured
    # here, before the incoming changes are applied.
    anchor = interval.last_done_on or interval.next_due_on - timedelta(days=interval.interval_days)

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(interval, field, value)

    # Changing the cadence re-derives the next occurrence, so "every 15 days"
    # -> "every 20 days" moves the next due date rather than leaving a date
    # computed under the old cadence. An explicit next_due_on in the same
    # request always wins.
    if "interval_days" in changes and "next_due_on" not in changes:
        interval.next_due_on = anchor + timedelta(days=interval.interval_days)

    interval.updated_at = datetime.now(UTC)
    return _to_interval_out(interval, today())


async def delete_interval(
    session: AsyncSession, user: CurrentUser, plant_id: UUID, interval_id: UUID
) -> None:
    await _resolve_plant(session, plant_id)
    await _authorize(session, user, plant_id, "update")
    interval = await _resolve_interval(session, plant_id, interval_id)
    # care_log.interval_id is ON DELETE SET NULL, so past completions survive
    # with their action_name snapshot intact.
    await session.delete(interval)


async def complete_interval(
    session: AsyncSession,
    user: CurrentUser,
    plant_id: UUID,
    interval_id: UUID,
    payload: CompleteRequest,
) -> CompleteResult:
    """Mark an action done and reschedule from the completion date.

    Rescheduling is deliberately anchored to when the action actually
    happened, not to when it was due: watering due on the 1st but done on the
    3rd of a 15-day cycle next falls due on the 18th, not the 16th. Anchoring
    to the due date instead would make a late user permanently late.
    """
    await _resolve_plant(session, plant_id)
    await _authorize(session, user, plant_id, "update")
    interval = await _resolve_interval(session, plant_id, interval_id)

    on_day = today()
    completed_on = payload.completed_on if payload.completed_on is not None else on_day
    if completed_on > on_day:
        raise AppError(
            status_code=400,
            code="modules.plants.future_date",
            title="Date is in the future",
            detail="completed_on cannot be in the future.",
        )
    if (on_day - completed_on).days > MAX_BACKDATE_DAYS:
        raise AppError(
            status_code=400,
            code="modules.plants.date_too_old",
            title="Date is too far in the past",
            detail=f"completed_on cannot be more than {MAX_BACKDATE_DAYS} days ago.",
        )

    log = CareLog(
        plant_id=plant_id,
        interval_id=interval.id,
        user_id=user.id,
        action_name=interval.name,
        due_on=interval.next_due_on,
        completed_on=completed_on,
        days_late=(completed_on - interval.next_due_on).days,
        note=payload.note,
    )
    session.add(log)

    interval.last_done_on = completed_on
    interval.next_due_on = completed_on + timedelta(days=interval.interval_days)
    interval.updated_at = datetime.now(UTC)
    await session.flush()

    publish_after_commit(
        session,
        CareCompleted(
            plant_id=plant_id,
            interval_id=interval.id,
            user_id=user.id,
            action_name=log.action_name,
            completed_on=completed_on,
            days_late=log.days_late,
        ),
    )
    return CompleteResult(log=_to_log_out(log), interval=_to_interval_out(interval, on_day))


# --------------------------------------------------------------------------
# Due summary (what the dashboard tile and the daily job both read)
# --------------------------------------------------------------------------


def summarize(count: int, overdue_count: int, max_days_overdue: int) -> str:
    if count == 0:
        return "Nothing due today"
    actions = "action" if count == 1 else "actions"
    if overdue_count and max_days_overdue > 0:
        days = "day" if max_days_overdue == 1 else "days"
        return f"{count} {actions} due, up to {max_days_overdue} {days} behind"
    return f"{count} {actions} due today"


async def _due_rows(
    session: AsyncSession, plant_ids: list[UUID], on_day: date, lookahead_days: int
) -> list[tuple[Plant, CareInterval]]:
    if not plant_ids:
        return []
    result = await session.execute(
        select(Plant, CareInterval)
        .join(CareInterval, CareInterval.plant_id == Plant.id)
        .where(
            Plant.id.in_(plant_ids),
            Plant.deleted_at.is_(None),
            CareInterval.active.is_(True),
            CareInterval.next_due_on <= on_day + timedelta(days=lookahead_days),
        )
        .order_by(CareInterval.next_due_on, Plant.name, CareInterval.name)
    )
    return [(plant, interval) for plant, interval in result.all()]


async def due_summary(
    session: AsyncSession, user: CurrentUser, *, lookahead_days: int = 0
) -> DueSummary:
    ids = await readable_ids(session, user_id=user.id, resource_type=RESOURCE_TYPE)
    on_day = today()
    rows = await _due_rows(session, [UUID(i) for i in ids], on_day, lookahead_days)

    items = [
        DueItem(
            plant_id=plant.id,
            plant_name=plant.name,
            interval_id=interval.id,
            action_name=interval.name,
            due_on=interval.next_due_on,
            days_overdue=_days_overdue(interval.next_due_on, on_day),
        )
        for plant, interval in rows
    ]
    items.sort(key=lambda item: (-item.days_overdue, item.plant_name, item.action_name))

    overdue = [item for item in items if item.days_overdue > 0]
    max_days_overdue = max((item.days_overdue for item in overdue), default=0)
    return DueSummary(
        day=on_day,
        count=len(items),
        overdue_count=len(overdue),
        max_days_overdue=max_days_overdue,
        summary=summarize(len(items), len(overdue), max_days_overdue),
        items=items,
    )


# --------------------------------------------------------------------------
# Calendar
# --------------------------------------------------------------------------


def parse_month(month: str) -> tuple[date, date]:
    try:
        year_str, month_str = month.split("-", 1)
        year, month_number = int(year_str), int(month_str)
        start = date(year, month_number, 1)
    except (ValueError, TypeError) as exc:
        raise AppError(
            status_code=400,
            code="modules.plants.invalid_month",
            title="Invalid month",
            detail="month must be formatted as YYYY-MM.",
        ) from exc
    last_day = calendar_module.monthrange(year, month_number)[1]
    return start, date(year, month_number, last_day)


async def month_calendar(session: AsyncSession, user: CurrentUser, *, month: str) -> CalendarOut:
    """Everything that happened, and everything scheduled, within one month.

    Past days come from `care_log` (fact). Today and later come from each
    active interval's `next_due_on` plus arithmetic repeats, tagged
    `projected` because completing early or late shifts every later
    occurrence — the projection is a forecast, not a commitment.
    """
    start, end = parse_month(month)
    ids = await readable_ids(session, user_id=user.id, resource_type=RESOURCE_TYPE)
    plant_ids = [UUID(resource_id) for resource_id in ids]
    if not plant_ids:
        return CalendarOut(month=month, start=start, end=end, entries=[])

    plant_result = await session.execute(
        select(Plant).where(Plant.id.in_(plant_ids), Plant.deleted_at.is_(None))
    )
    names = {plant.id: plant.name for plant in plant_result.scalars()}
    if not names:
        return CalendarOut(month=month, start=start, end=end, entries=[])

    entries: list[CalendarEntry] = []

    log_result = await session.execute(
        select(CareLog)
        .where(
            CareLog.plant_id.in_(list(names)),
            CareLog.completed_on >= start,
            CareLog.completed_on <= end,
        )
        .order_by(CareLog.completed_on, CareLog.action_name)
    )
    for log in log_result.scalars():
        entries.append(
            CalendarEntry(
                day=log.completed_on,
                kind="done",
                plant_id=log.plant_id,
                plant_name=names[log.plant_id],
                interval_id=log.interval_id,
                action_name=log.action_name,
                log_id=log.id,
                days_late=log.days_late,
            )
        )

    on_day = today()
    interval_result = await session.execute(
        select(CareInterval)
        .where(CareInterval.plant_id.in_(list(names)), CareInterval.active.is_(True))
        .order_by(CareInterval.next_due_on, CareInterval.name)
    )
    for interval in interval_result.scalars():
        entries.extend(_project(interval, names[interval.plant_id], start, end, on_day))

    entries.sort(key=lambda entry: (entry.day, entry.plant_name, entry.action_name))
    return CalendarOut(month=month, start=start, end=end, entries=entries[:MAX_CALENDAR_ENTRIES])


def _project(
    interval: CareInterval, plant_name: str, start: date, end: date, on_day: date
) -> list[CalendarEntry]:
    """The interval's own next_due_on, plus arithmetic repeats inside [start, end]."""

    def entry(day: date, kind: str) -> CalendarEntry:
        return CalendarEntry(
            day=day,
            kind=kind,  # type: ignore[arg-type]
            plant_id=interval.plant_id,
            plant_name=plant_name,
            interval_id=interval.id,
            action_name=interval.name,
        )

    out: list[CalendarEntry] = []
    anchor = interval.next_due_on
    if start <= anchor <= end:
        out.append(entry(anchor, "overdue" if anchor < on_day else "due"))

    # Repeats are only meaningful from today forward: a "projected" repeat
    # dated in the past never happened (there would be a care_log row if it
    # had), so it would be pure noise on the calendar. Starting the loop at
    # `lower` also bounds it to the month regardless of how stale `anchor` is.
    lower = max(start, on_day)
    if lower > end:
        return out
    step = interval.interval_days
    gap = (lower - anchor).days
    repeat = max(1, -(-gap // step))  # ceil division: first repeat landing on/after `lower`
    while True:
        day = anchor + timedelta(days=step * repeat)
        if day > end:
            return out
        if day >= lower:
            out.append(entry(day, "projected"))
        repeat += 1


# --------------------------------------------------------------------------
# Photos
# --------------------------------------------------------------------------


async def set_plant_image(
    session: AsyncSession, user: CurrentUser, plant_id: UUID, *, data: bytes
) -> PlantOut:
    plant = await _resolve_plant(session, plant_id)
    await _authorize(session, user, plant_id, "update")

    max_bytes = get_plants_settings().max_image_bytes
    if not data:
        raise AppError(
            status_code=400,
            code="modules.plants.empty_image",
            title="Empty upload",
            detail="The uploaded file contained no data.",
        )
    if len(data) > max_bytes:
        raise AppError(
            status_code=413,
            code="modules.plants.image_too_large",
            title="Image too large",
            detail=f"Images must be at most {max_bytes // 1024} KiB.",
        )

    # The declared Content-Type is ignored: what gets served back later is
    # decided by what the bytes actually are.
    content_type = sniff_image_type(data[:16])
    if content_type is None:
        raise AppError(
            status_code=415,
            code="modules.plants.unsupported_image",
            title="Unsupported image type",
            detail="Images must be JPEG, PNG, WebP or GIF.",
        )

    plant.image_path = write_image(plant_id, data, content_type)
    plant.image_content_type = content_type
    now = datetime.now(UTC)
    plant.image_updated_at = now
    plant.updated_at = now

    intervals = (await _intervals_for(session, [plant_id])).get(plant_id, [])
    return _to_plant_out(plant, intervals, today())


async def clear_plant_image(session: AsyncSession, user: CurrentUser, plant_id: UUID) -> None:
    plant = await _resolve_plant(session, plant_id)
    await _authorize(session, user, plant_id, "update")

    remove_image(plant_id)
    plant.image_path = None
    plant.image_content_type = None
    plant.image_updated_at = None
    plant.updated_at = datetime.now(UTC)


async def get_plant_image(
    session: AsyncSession, user: CurrentUser, plant_id: UUID
) -> tuple[Path, str]:
    plant = await _resolve_plant(session, plant_id)
    await _authorize(session, user, plant_id, "read")

    path = absolute_path(plant.image_path) if plant.image_path else None
    if path is None or not path.is_file():
        raise AppError(
            status_code=404,
            code="modules.plants.no_image",
            title="No image",
            detail="This plant has no image.",
        )
    return path, plant.image_content_type or "application/octet-stream"


async def list_history(
    session: AsyncSession, user: CurrentUser, plant_id: UUID, *, limit: int
) -> list[CareLogOut]:
    await _resolve_plant(session, plant_id)
    await _authorize(session, user, plant_id, "read")
    result = await session.execute(
        select(CareLog)
        .where(CareLog.plant_id == plant_id)
        .order_by(CareLog.completed_on.desc(), CareLog.created_at.desc())
        .limit(limit)
    )
    return [_to_log_out(log) for log in result.scalars()]
