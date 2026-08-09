"""Plant care module.

The load-bearing rule under test throughout is *rescheduling anchors to the
completion date, not the due date*: an action due on the 1st of a 15-day cycle
that is actually done on the 3rd next falls due on the 18th, not the 16th.
Anchoring to the due date would make a user who runs late permanently late.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core import events as events_module
from disp.core.auth import Permission, grant
from disp.core.config import get_settings
from disp.core.contract import TileContext
from disp.core.errors import AppError
from disp.core.events import EventBus, set_event_bus
from disp.core.settings_store import SettingsStore
from disp.modules.plants import reminders, service
from disp.modules.plants.config import get_plants_settings
from disp.modules.plants.models import CareInterval, CareLog
from disp.modules.plants.schemas import (
    CareIntervalCreate,
    CareIntervalUpdate,
    CompleteRequest,
    PlantCreate,
    PlantUpdate,
)
from disp.modules.plants.tiles import plants_due_tile
from tests.factories import current_user_for, make_user

# A fixed "today" so every date assertion below is exact rather than relative.
TODAY = date(2026, 3, 1)

# Smallest valid files of each type, for the upload path.
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)
JPEG_HEAD = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture(autouse=True)
def _fresh_event_bus() -> Iterator[None]:
    previous = events_module._active_bus
    set_event_bus(EventBus())
    yield
    events_module._active_bus = previous


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin `service.today()`.

    Every other module reaches "today" through this one function
    (`reminders` deliberately calls `service.today()` rather than importing
    the name), so this single patch fixes the date for the whole module.
    """
    monkeypatch.setattr(service, "today", lambda: TODAY)


@pytest.fixture
def media_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = tmp_path / "media"
    monkeypatch.setenv("DISP_PLANTS_MEDIA_ROOT", str(root))
    get_plants_settings.cache_clear()
    yield root
    get_plants_settings.cache_clear()


async def _owner(session: AsyncSession, email: str):
    user = await make_user(session, email=email)
    return current_user_for(user)


async def _plant_with_intervals(
    session: AsyncSession, cu, name: str = "Sansevieria", **intervals: int
):
    """Create a plant plus named intervals, each anchored to `last_done_on=TODAY`."""
    plant = await service.create_plant(session, cu, PlantCreate(name=name))
    for label, days in intervals.items():
        await service.add_interval(
            session,
            cu,
            plant.id,
            CareIntervalCreate(name=label, interval_days=days, last_done_on=TODAY),
        )
    return plant


# --------------------------------------------------------------------------
# Setting a plant up
# --------------------------------------------------------------------------


async def test_create_plant_grants_owner_and_emits_event(db_session: AsyncSession) -> None:
    from disp.core.auth import can
    from disp.modules.plants.events import PlantCreated

    received: list[PlantCreated] = []

    async def _handler(event: PlantCreated) -> None:
        received.append(event)

    bus = EventBus()
    bus.subscribe(PlantCreated, _handler)
    set_event_bus(bus)

    cu = await _owner(db_session, "plants-create@example.com")
    plant = await service.create_plant(
        db_session, cu, PlantCreate(name="Sansevieria", care_notes="Bright indirect light.")
    )
    await db_session.commit()

    assert await can(db_session, cu, "read", "plants.plant", str(plant.id)) is True
    for task in list(events_module._background_tasks):
        await task
    assert [event.plant_id for event in received] == [plant.id]


async def test_plant_can_be_created_bare_then_filled_in_later(db_session: AsyncSession) -> None:
    """The user's stated flow: name only up front, notes and description later."""
    cu = await _owner(db_session, "plants-later@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    assert plant.care_notes is None

    updated = await service.update_plant(
        db_session,
        cu,
        plant.id,
        PlantUpdate(care_notes="Water sparingly. Never let it sit wet.", description="Hallway"),
    )
    assert updated.care_notes == "Water sparingly. Never let it sit wet."
    assert updated.description == "Hallway"


async def test_interval_first_due_is_last_done_plus_interval(db_session: AsyncSession) -> None:
    cu = await _owner(db_session, "plants-interval@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))

    water = await service.add_interval(
        db_session, cu, plant.id, CareIntervalCreate(name="Water", interval_days=15)
    )
    fertilizer = await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(name="Green Fertilizer", interval_days=30, last_done_on=TODAY),
    )

    assert water.next_due_on == TODAY + timedelta(days=15)
    assert fertilizer.next_due_on == TODAY + timedelta(days=30)
    # Nothing is due on the day it was set up.
    assert water.days_overdue == -15


async def test_interval_anchored_to_a_past_last_done_is_already_due(
    db_session: AsyncSession,
) -> None:
    """ "I last watered it 20 days ago" must land in the past, not the future."""
    cu = await _owner(db_session, "plants-backdated@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Ficus"))

    water = await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(name="Water", interval_days=15, last_done_on=TODAY - timedelta(days=20)),
    )
    assert water.next_due_on == TODAY - timedelta(days=5)
    assert water.days_overdue == 5


async def test_future_last_done_is_rejected(db_session: AsyncSession) -> None:
    cu = await _owner(db_session, "plants-future@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Ficus"))

    with pytest.raises(AppError) as exc:
        await service.add_interval(
            db_session,
            cu,
            plant.id,
            CareIntervalCreate(
                name="Water", interval_days=15, last_done_on=TODAY + timedelta(days=1)
            ),
        )
    assert exc.value.status_code == 400
    assert exc.value.code == "modules.plants.future_date"


# --------------------------------------------------------------------------
# The rescheduling rule
# --------------------------------------------------------------------------


async def test_completing_late_reschedules_from_the_completion_date(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Due the 1st, done the 3rd, 15-day cycle -> next due the 18th (not the 16th)."""
    cu = await _owner(db_session, "plants-reschedule@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    water = await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(name="Water", interval_days=15, last_done_on=date(2026, 2, 14)),
    )
    assert water.next_due_on == date(2026, 3, 1)

    # Two days pass with the action untouched.
    monkeypatch.setattr(service, "today", lambda: date(2026, 3, 3))
    result = await service.complete_interval(db_session, cu, plant.id, water.id, CompleteRequest())

    assert result.log.due_on == date(2026, 3, 1)
    assert result.log.completed_on == date(2026, 3, 3)
    assert result.log.days_late == 2
    assert result.interval.next_due_on == date(2026, 3, 18)
    assert result.interval.last_done_on == date(2026, 3, 3)


async def test_overdue_count_grows_each_day_until_the_action_is_done(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Day 2 says "1 day behind", day 3 says "2 days behind", then it clears."""
    cu = await _owner(db_session, "plants-behind@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    water = await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(name="Water", interval_days=15, last_done_on=date(2026, 2, 14)),
    )

    for day, expected_overdue in [(1, 0), (2, 1), (3, 2)]:
        monkeypatch.setattr(service, "today", lambda d=day: date(2026, 3, d))
        summary = await service.due_summary(db_session, cu)
        assert summary.count == 1
        assert summary.items[0].days_overdue == expected_overdue

    assert summary.summary == "1 action due, up to 2 days behind"

    await service.complete_interval(db_session, cu, plant.id, water.id, CompleteRequest())
    assert (await service.due_summary(db_session, cu)).count == 0
    assert (await service.due_summary(db_session, cu)).summary == "Nothing due today"


async def test_completing_early_also_reschedules_from_completion(
    db_session: AsyncSession,
) -> None:
    cu = await _owner(db_session, "plants-early@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Aloe"))
    water = await service.add_interval(
        db_session, cu, plant.id, CareIntervalCreate(name="Water", interval_days=15)
    )
    assert water.next_due_on == TODAY + timedelta(days=15)

    result = await service.complete_interval(db_session, cu, plant.id, water.id, CompleteRequest())
    assert result.log.days_late == -15
    assert result.interval.next_due_on == TODAY + timedelta(days=15)


async def test_completion_can_be_backdated_but_not_future_dated(
    db_session: AsyncSession,
) -> None:
    cu = await _owner(db_session, "plants-backdate@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Aloe"))
    water = await service.add_interval(
        db_session, cu, plant.id, CareIntervalCreate(name="Water", interval_days=10)
    )

    result = await service.complete_interval(
        db_session,
        cu,
        plant.id,
        water.id,
        CompleteRequest(completed_on=TODAY - timedelta(days=3)),
    )
    assert result.interval.next_due_on == TODAY + timedelta(days=7)

    with pytest.raises(AppError) as exc:
        await service.complete_interval(
            db_session,
            cu,
            plant.id,
            water.id,
            CompleteRequest(completed_on=TODAY + timedelta(days=1)),
        )
    assert exc.value.code == "modules.plants.future_date"

    with pytest.raises(AppError) as too_old:
        await service.complete_interval(
            db_session,
            cu,
            plant.id,
            water.id,
            CompleteRequest(completed_on=TODAY - timedelta(days=400)),
        )
    assert too_old.value.code == "modules.plants.date_too_old"


async def test_changing_the_cadence_rederives_the_next_due_date(
    db_session: AsyncSession,
) -> None:
    cu = await _owner(db_session, "plants-cadence@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Monstera"))
    water = await service.add_interval(
        db_session, cu, plant.id, CareIntervalCreate(name="Water", interval_days=15)
    )
    assert water.next_due_on == TODAY + timedelta(days=15)

    widened = await service.update_interval(
        db_session, cu, plant.id, water.id, CareIntervalUpdate(interval_days=20)
    )
    assert widened.next_due_on == TODAY + timedelta(days=20)

    # An explicit date in the same request wins over the re-derivation.
    pinned = await service.update_interval(
        db_session,
        cu,
        plant.id,
        water.id,
        CareIntervalUpdate(interval_days=30, next_due_on=date(2026, 4, 2)),
    )
    assert pinned.next_due_on == date(2026, 4, 2)


async def test_inactive_intervals_are_never_due(db_session: AsyncSession) -> None:
    cu = await _owner(db_session, "plants-inactive@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Cactus"))
    water = await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(name="Water", interval_days=5, last_done_on=TODAY - timedelta(days=30)),
    )
    assert (await service.due_summary(db_session, cu)).count == 1

    await service.update_interval(
        db_session, cu, plant.id, water.id, CareIntervalUpdate(active=False)
    )
    assert (await service.due_summary(db_session, cu)).count == 0


# --------------------------------------------------------------------------
# Due summary across several plants
# --------------------------------------------------------------------------


async def test_due_summary_spans_plants_and_sorts_most_overdue_first(
    db_session: AsyncSession,
) -> None:
    cu = await _owner(db_session, "plants-summary@example.com")

    sansevieria = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    await service.add_interval(
        db_session,
        cu,
        sansevieria.id,
        CareIntervalCreate(name="Water", interval_days=15, last_done_on=TODAY - timedelta(days=17)),
    )
    await service.add_interval(
        db_session,
        cu,
        sansevieria.id,
        CareIntervalCreate(
            name="Green Fertilizer", interval_days=30, last_done_on=TODAY - timedelta(days=30)
        ),
    )
    fern = await service.create_plant(db_session, cu, PlantCreate(name="Fern"))
    await service.add_interval(
        db_session,
        cu,
        fern.id,
        CareIntervalCreate(name="Water", interval_days=7, last_done_on=TODAY - timedelta(days=100)),
    )

    summary = await service.due_summary(db_session, cu)
    assert summary.count == 3
    # Green Fertilizer falls due exactly today, so it is due but not *behind*.
    assert summary.overdue_count == 2
    # Fern is 93 days behind, so it leads.
    assert summary.items[0].plant_name == "Fern"
    assert summary.items[0].days_overdue == 93
    # Then most-behind first within the remaining: Water is 2 days late,
    # Green Fertilizer is due today.
    assert [(i.action_name, i.days_overdue) for i in summary.items[1:]] == [
        ("Water", 2),
        ("Green Fertilizer", 0),
    ]
    assert summary.summary == "3 actions due, up to 93 days behind"


async def test_plant_rollups_badge_the_list_view(db_session: AsyncSession) -> None:
    cu = await _owner(db_session, "plants-rollup@example.com")
    plant = await _plant_with_intervals(db_session, cu, Water=15)
    await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(name="Feed", interval_days=30, last_done_on=TODAY - timedelta(days=32)),
    )

    page = await service.list_plants(db_session, cu, limit=20, cursor=None, q=None)
    assert len(page.items) == 1
    assert page.items[0].due_count == 1
    assert page.items[0].max_days_overdue == 2
    assert page.items[0].next_due_on == TODAY - timedelta(days=2)


async def test_list_plants_filters_by_name_and_hides_deleted(db_session: AsyncSession) -> None:
    cu = await _owner(db_session, "plants-list@example.com")
    await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    fern = await service.create_plant(db_session, cu, PlantCreate(name="Boston Fern"))

    matched = await service.list_plants(db_session, cu, limit=20, cursor=None, q="fern")
    assert [p.name for p in matched.items] == ["Boston Fern"]

    await service.delete_plant(db_session, cu, fern.id)
    remaining = await service.list_plants(db_session, cu, limit=20, cursor=None, q=None)
    assert [p.name for p in remaining.items] == ["Sansevieria"]
    with pytest.raises(AppError) as exc:
        await service.get_plant(db_session, cu, fern.id)
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------
# Access control
# --------------------------------------------------------------------------


async def test_another_users_plant_is_invisible(db_session: AsyncSession) -> None:
    owner = await _owner(db_session, "plants-owner@example.com")
    stranger = await _owner(db_session, "plants-stranger@example.com")
    plant = await service.create_plant(db_session, owner, PlantCreate(name="Sansevieria"))

    with pytest.raises(AppError) as exc:
        await service.get_plant(db_session, stranger, plant.id)
    assert exc.value.status_code == 404
    assert (
        await service.list_plants(db_session, stranger, limit=20, cursor=None, q=None)
    ).items == []
    assert (await service.due_summary(db_session, stranger)).count == 0


async def test_read_share_permits_reading_but_not_completing(db_session: AsyncSession) -> None:
    owner = await _owner(db_session, "plants-share-owner@example.com")
    guest = await _owner(db_session, "plants-share-guest@example.com")
    plant = await service.create_plant(db_session, owner, PlantCreate(name="Sansevieria"))
    water = await service.add_interval(
        db_session, owner, plant.id, CareIntervalCreate(name="Water", interval_days=15)
    )

    await grant(
        db_session,
        resource_type="plants.plant",
        resource_id=str(plant.id),
        user_id=guest.id,
        permission=Permission.READ,
        granted_by=owner.id,
    )

    assert (await service.get_plant(db_session, guest, plant.id)).name == "Sansevieria"
    with pytest.raises(AppError) as exc:
        await service.complete_interval(db_session, guest, plant.id, water.id, CompleteRequest())
    assert exc.value.status_code == 403
    assert exc.value.code == "core.acl.forbidden"


async def test_interval_from_another_plant_is_not_addressable(db_session: AsyncSession) -> None:
    cu = await _owner(db_session, "plants-crossplant@example.com")
    first = await service.create_plant(db_session, cu, PlantCreate(name="One"))
    second = await service.create_plant(db_session, cu, PlantCreate(name="Two"))
    water = await service.add_interval(
        db_session, cu, second.id, CareIntervalCreate(name="Water", interval_days=15)
    )

    with pytest.raises(AppError) as exc:
        await service.complete_interval(db_session, cu, first.id, water.id, CompleteRequest())
    assert exc.value.status_code == 404
    assert exc.value.code == "modules.plants.interval_not_found"


# --------------------------------------------------------------------------
# History and the calendar
# --------------------------------------------------------------------------


async def test_deleting_an_interval_keeps_its_completed_history(
    db_session: AsyncSession,
) -> None:
    cu = await _owner(db_session, "plants-history@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    water = await service.add_interval(
        db_session, cu, plant.id, CareIntervalCreate(name="Water", interval_days=15)
    )
    await service.complete_interval(db_session, cu, plant.id, water.id, CompleteRequest())

    await service.delete_interval(db_session, cu, plant.id, water.id)
    await db_session.flush()

    history = await service.list_history(db_session, cu, plant.id, limit=50)
    assert len(history) == 1
    # The FK went null but the snapshotted label survived.
    assert history[0].interval_id is None
    assert history[0].action_name == "Water"


async def test_calendar_shows_completed_past_and_projected_future(
    db_session: AsyncSession,
) -> None:
    cu = await _owner(db_session, "plants-calendar@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    water = await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(name="Water", interval_days=15, last_done_on=date(2026, 2, 14)),
    )
    # Completed on the 1st: due today, done today.
    await service.complete_interval(db_session, cu, plant.id, water.id, CompleteRequest())

    result = await service.month_calendar(db_session, cu, month="2026-03")
    assert result.start == date(2026, 3, 1)
    assert result.end == date(2026, 3, 31)

    by_kind: dict[str, list[date]] = {}
    for entry in result.entries:
        by_kind.setdefault(entry.kind, []).append(entry.day)

    assert by_kind["done"] == [date(2026, 3, 1)]
    # Next due is the 16th (done on the 1st + 15), then one projected repeat.
    assert by_kind["due"] == [date(2026, 3, 16)]
    assert by_kind["projected"] == [date(2026, 3, 31)]


async def test_calendar_marks_a_missed_action_overdue(db_session: AsyncSession) -> None:
    cu = await _owner(db_session, "plants-cal-overdue@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(name="Water", interval_days=15, last_done_on=date(2026, 2, 10)),
    )

    result = await service.month_calendar(db_session, cu, month="2026-02")
    overdue = [e for e in result.entries if e.kind == "overdue"]
    assert [e.day for e in overdue] == [date(2026, 2, 25)]


async def test_calendar_for_a_past_month_projects_nothing(db_session: AsyncSession) -> None:
    """A past month is history only — a projection there never happened."""
    cu = await _owner(db_session, "plants-cal-past@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    await service.add_interval(
        db_session, cu, plant.id, CareIntervalCreate(name="Water", interval_days=3)
    )

    result = await service.month_calendar(db_session, cu, month="2026-01")
    assert result.entries == []


async def test_calendar_rejects_a_malformed_month(db_session: AsyncSession) -> None:
    cu = await _owner(db_session, "plants-cal-bad@example.com")
    with pytest.raises(AppError) as exc:
        await service.month_calendar(db_session, cu, month="2026-13")
    assert exc.value.status_code == 400
    assert exc.value.code == "modules.plants.invalid_month"


async def test_calendar_projection_is_bounded_for_a_daily_interval(
    db_session: AsyncSession,
) -> None:
    """A 1-day cadence anchored far in the past must not iterate from the anchor."""
    cu = await _owner(db_session, "plants-cal-daily@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Seedling"))
    await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(name="Mist", interval_days=1, last_done_on=date(2020, 1, 1)),
    )

    result = await service.month_calendar(db_session, cu, month="2026-03")
    days = sorted({entry.day for entry in result.entries})
    # Every day from today to month end, and nothing before today.
    assert days[0] == TODAY
    assert days[-1] == date(2026, 3, 31)
    assert len(result.entries) <= service.MAX_CALENDAR_ENTRIES


# --------------------------------------------------------------------------
# Dashboard tile
# --------------------------------------------------------------------------


async def test_tile_summarises_what_is_due(db_session: AsyncSession) -> None:
    cu = await _owner(db_session, "plants-tile@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(name="Water", interval_days=15, last_done_on=TODAY - timedelta(days=17)),
    )
    await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(
            name="Green Fertilizer", interval_days=30, last_done_on=TODAY - timedelta(days=30)
        ),
    )

    ctx = TileContext(
        user=cu,
        session=db_session,
        platform=SimpleNamespace(),  # type: ignore[arg-type]
        now=datetime.now(UTC),
    )
    tile = await plants_due_tile(ctx)

    assert tile.key == "plants.due"
    assert tile.count == 2
    assert tile.items[0].primary == "Water — Sansevieria"
    assert tile.items[0].secondary == "2 days behind"
    assert tile.items[1].primary == "Green Fertilizer — Sansevieria"
    assert tile.items[1].secondary == "due today"
    assert tile.items[0].href == f"/api/plants/{plant.id}"


async def test_tile_is_empty_when_nothing_is_due(db_session: AsyncSession) -> None:
    cu = await _owner(db_session, "plants-tile-empty@example.com")
    await _plant_with_intervals(db_session, cu, Water=15)

    ctx = TileContext(
        user=cu,
        session=db_session,
        platform=SimpleNamespace(),  # type: ignore[arg-type]
        now=datetime.now(UTC),
    )
    tile = await plants_due_tile(ctx)
    assert tile.count == 0
    assert tile.items == []
    assert tile.empty_text == "Nothing due today"


# --------------------------------------------------------------------------
# Daily reminder job
# --------------------------------------------------------------------------


class _RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[UUID, str, str, str]] = []

    async def send(
        self, user_id: UUID, notification_type: str, title: str, body: str, url: str | None = None
    ) -> None:
        self.sent.append((user_id, notification_type, title, body))


def _platform(notifier: _RecordingNotifier) -> SimpleNamespace:
    store = SettingsStore(Fernet(get_settings().settings_key.get_secret_value()))
    return SimpleNamespace(store=store, notifier=notifier)


async def test_daily_job_sends_one_digest_per_user(db_session: AsyncSession) -> None:
    cu = await _owner(db_session, "plants-daily@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(name="Water", interval_days=15, last_done_on=TODAY - timedelta(days=17)),
    )
    await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(
            name="Green Fertilizer", interval_days=30, last_done_on=TODAY - timedelta(days=30)
        ),
    )
    await db_session.flush()

    notifier = _RecordingNotifier()
    sent = await reminders.notify_due(db_session, _platform(notifier))  # type: ignore[arg-type]

    mine = [row for row in notifier.sent if row[0] == cu.id]
    assert sent >= 1
    assert len(mine) == 1
    _, notification_type, title, body = mine[0]
    assert notification_type == "plants.care_due"
    assert title == "2 actions due, up to 2 days behind"
    assert body.splitlines() == [
        "• Water — Sansevieria (2 days behind)",
        "• Green Fertilizer — Sansevieria (due today)",
    ]


async def test_daily_job_skips_a_user_who_turned_the_push_off(
    db_session: AsyncSession,
) -> None:
    cu = await _owner(db_session, "plants-daily-off@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(name="Water", interval_days=15, last_done_on=TODAY - timedelta(days=20)),
    )
    await db_session.flush()

    notifier = _RecordingNotifier()
    platform = _platform(notifier)
    await platform.store.set(
        db_session, user_id=cu.id, domain="plants", key="reminders.daily_push", value=False
    )

    await reminders.notify_due(db_session, platform)  # type: ignore[arg-type]
    assert [row for row in notifier.sent if row[0] == cu.id] == []


async def test_daily_job_stays_quiet_when_nothing_is_due(db_session: AsyncSession) -> None:
    cu = await _owner(db_session, "plants-daily-quiet@example.com")
    await _plant_with_intervals(db_session, cu, Water=15)
    await db_session.flush()

    notifier = _RecordingNotifier()
    await reminders.notify_due(db_session, _platform(notifier))  # type: ignore[arg-type]
    assert [row for row in notifier.sent if row[0] == cu.id] == []


async def test_daily_job_look_ahead_setting_widens_the_digest(
    db_session: AsyncSession,
) -> None:
    cu = await _owner(db_session, "plants-daily-ahead@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    await service.add_interval(
        db_session,
        cu,
        plant.id,
        CareIntervalCreate(name="Water", interval_days=3),  # due in 3 days
    )
    await db_session.flush()

    notifier = _RecordingNotifier()
    platform = _platform(notifier)
    await reminders.notify_due(db_session, platform)  # type: ignore[arg-type]
    assert [row for row in notifier.sent if row[0] == cu.id] == []

    await platform.store.set(
        db_session,
        user_id=cu.id,
        domain="plants",
        key="reminders.include_upcoming_days",
        value=5,
    )
    await reminders.notify_due(db_session, platform)  # type: ignore[arg-type]
    assert len([row for row in notifier.sent if row[0] == cu.id]) == 1


# --------------------------------------------------------------------------
# Photos
# --------------------------------------------------------------------------


async def test_image_round_trips_through_the_media_root(
    db_session: AsyncSession, media_dir: Path
) -> None:
    cu = await _owner(db_session, "plants-image@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))

    updated = await service.set_plant_image(db_session, cu, plant.id, data=PNG_1PX)
    assert updated.has_image is True
    assert updated.image_url == f"/api/plants/{plant.id}/image"
    assert (media_dir / f"{plant.id}.png").read_bytes() == PNG_1PX

    path, content_type = await service.get_plant_image(db_session, cu, plant.id)
    assert content_type == "image/png"
    assert path.read_bytes() == PNG_1PX


async def test_image_survives_a_relative_media_root(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The configured default (`var/media/plants`) is a *relative* path.

    Regression: `_variant_paths` used to build unresolved paths while the
    write target was resolved, so the post-write cleanup saw the file it had
    just written as a stale variant and deleted it. Only reproducible with a
    relative root — `tmp_path` is absolute and already resolved, so every
    other image test here passed straight through the bug.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DISP_PLANTS_MEDIA_ROOT", "var/media/plants")
    get_plants_settings.cache_clear()
    try:
        cu = await _owner(db_session, "plants-image-relative@example.com")
        plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
        await service.set_plant_image(db_session, cu, plant.id, data=PNG_1PX)

        path, _ = await service.get_plant_image(db_session, cu, plant.id)
        assert path.is_file()
        assert path.read_bytes() == PNG_1PX
    finally:
        get_plants_settings.cache_clear()


async def test_replacing_an_image_with_another_format_leaves_no_orphan(
    db_session: AsyncSession, media_dir: Path
) -> None:
    cu = await _owner(db_session, "plants-image-replace@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))

    await service.set_plant_image(db_session, cu, plant.id, data=PNG_1PX)
    await service.set_plant_image(db_session, cu, plant.id, data=JPEG_HEAD)

    assert not (media_dir / f"{plant.id}.png").exists()
    assert (media_dir / f"{plant.id}.jpg").exists()
    _, content_type = await service.get_plant_image(db_session, cu, plant.id)
    assert content_type == "image/jpeg"


async def test_image_type_is_sniffed_not_taken_on_trust(
    db_session: AsyncSession, media_dir: Path
) -> None:
    cu = await _owner(db_session, "plants-image-sniff@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))

    with pytest.raises(AppError) as exc:
        await service.set_plant_image(db_session, cu, plant.id, data=b"<html>not an image</html>")
    assert exc.value.status_code == 415
    assert exc.value.code == "modules.plants.unsupported_image"
    # Rejected before anything touched the disk.
    assert not media_dir.exists() or list(media_dir.glob("*")) == []


async def test_oversized_image_is_rejected(
    db_session: AsyncSession, media_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DISP_PLANTS_MAX_IMAGE_BYTES", "128")
    get_plants_settings.cache_clear()

    cu = await _owner(db_session, "plants-image-big@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))

    with pytest.raises(AppError) as exc:
        await service.set_plant_image(db_session, cu, plant.id, data=PNG_1PX + b"\x00" * 200)
    assert exc.value.status_code == 413
    assert exc.value.code == "modules.plants.image_too_large"


async def test_deleting_an_image_removes_the_file_and_the_pointer(
    db_session: AsyncSession, media_dir: Path
) -> None:
    cu = await _owner(db_session, "plants-image-del@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    await service.set_plant_image(db_session, cu, plant.id, data=PNG_1PX)

    await service.clear_plant_image(db_session, cu, plant.id)
    assert not (media_dir / f"{plant.id}.png").exists()

    with pytest.raises(AppError) as exc:
        await service.get_plant_image(db_session, cu, plant.id)
    assert exc.value.status_code == 404
    assert exc.value.code == "modules.plants.no_image"


async def test_image_of_a_plant_you_cannot_see_is_a_404(
    db_session: AsyncSession, media_dir: Path
) -> None:
    owner = await _owner(db_session, "plants-image-owner@example.com")
    stranger = await _owner(db_session, "plants-image-stranger@example.com")
    plant = await service.create_plant(db_session, owner, PlantCreate(name="Sansevieria"))
    await service.set_plant_image(db_session, owner, plant.id, data=PNG_1PX)

    with pytest.raises(AppError) as exc:
        await service.get_plant_image(db_session, stranger, plant.id)
    assert exc.value.status_code == 404
    assert exc.value.code == "modules.plants.not_found"


# --------------------------------------------------------------------------
# Cascades
# --------------------------------------------------------------------------


async def test_unknown_plant_and_interval_ids_are_404(db_session: AsyncSession) -> None:
    cu = await _owner(db_session, "plants-unknown@example.com")
    with pytest.raises(AppError) as exc:
        await service.get_plant(db_session, cu, uuid4())
    assert exc.value.status_code == 404


async def test_intervals_and_logs_are_scoped_to_their_plant(db_session: AsyncSession) -> None:
    cu = await _owner(db_session, "plants-scoped@example.com")
    plant = await service.create_plant(db_session, cu, PlantCreate(name="Sansevieria"))
    water = await service.add_interval(
        db_session, cu, plant.id, CareIntervalCreate(name="Water", interval_days=15)
    )
    await service.complete_interval(db_session, cu, plant.id, water.id, CompleteRequest())
    await db_session.flush()

    intervals = (
        await db_session.execute(select(CareInterval).where(CareInterval.plant_id == plant.id))
    ).scalars()
    logs = (await db_session.execute(select(CareLog).where(CareLog.plant_id == plant.id))).scalars()
    assert len(list(intervals)) == 1
    assert len(list(logs)) == 1
