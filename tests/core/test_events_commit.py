from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core import events as events_module
from disp.core.events import EventBus, publish_after_commit


@dataclass(frozen=True, slots=True)
class _ProbeEvent:
    value: int


@pytest.fixture(autouse=True)
def _fresh_event_bus() -> None:
    previous = events_module._active_bus
    yield
    events_module._active_bus = previous


# Case 37: publish_after_commit dispatches only after commit and not after
# rollback.


async def test_publish_after_commit_dispatches_only_after_commit(
    db_session: AsyncSession,
) -> None:
    bus = EventBus()
    received: list[_ProbeEvent] = []

    async def handler(event: _ProbeEvent) -> None:
        received.append(event)

    bus.subscribe(_ProbeEvent, handler)
    events_module.set_event_bus(bus)

    await db_session.execute(text("SELECT 1"))
    publish_after_commit(db_session, _ProbeEvent(value=1))
    assert received == []

    await db_session.commit()
    for task in list(events_module._background_tasks):
        await task

    assert received == [_ProbeEvent(value=1)]


async def test_publish_after_commit_does_not_dispatch_after_rollback(
    db_session: AsyncSession,
) -> None:
    bus = EventBus()
    received: list[_ProbeEvent] = []

    async def handler(event: _ProbeEvent) -> None:
        received.append(event)

    bus.subscribe(_ProbeEvent, handler)
    events_module.set_event_bus(bus)

    await db_session.execute(text("SELECT 1"))
    publish_after_commit(db_session, _ProbeEvent(value=2))

    await db_session.rollback()
    for task in list(events_module._background_tasks):
        await task

    assert received == []
