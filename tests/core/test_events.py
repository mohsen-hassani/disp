from dataclasses import dataclass

import pytest

from disp.core import events as events_module
from disp.core.events import EventBus, HandlerFailure


@dataclass(frozen=True, slots=True)
class SampleEvent:
    value: int


@dataclass(frozen=True, slots=True)
class OtherEvent:
    value: int


async def test_subscribed_handler_receives_published_event() -> None:
    bus = EventBus()
    received: list[SampleEvent] = []

    async def handler(event: SampleEvent) -> None:
        received.append(event)

    bus.subscribe(SampleEvent, handler)
    failures = await bus.publish(SampleEvent(value=1))

    assert received == [SampleEvent(value=1)]
    assert failures == []


async def test_sync_handler_is_supported() -> None:
    bus = EventBus()
    received: list[SampleEvent] = []

    def handler(event: SampleEvent) -> None:
        received.append(event)

    bus.subscribe(SampleEvent, handler)
    await bus.publish(SampleEvent(value=2))

    assert received == [SampleEvent(value=2)]


async def test_dispatch_matches_exact_type_only() -> None:
    bus = EventBus()
    received: list[SampleEvent] = []

    bus.subscribe(SampleEvent, lambda e: received.append(e))
    await bus.publish(OtherEvent(value=1))  # type: ignore[arg-type]

    assert received == []


async def test_raising_handler_does_not_block_others_and_returns_failure() -> None:
    bus = EventBus()
    order: list[str] = []

    def failing_handler(event: SampleEvent) -> None:
        order.append("failing")
        raise RuntimeError("boom")

    def second_handler(event: SampleEvent) -> None:
        order.append("second")

    bus.subscribe(SampleEvent, failing_handler)
    bus.subscribe(SampleEvent, second_handler)

    failures = await bus.publish(SampleEvent(value=1))

    assert order == ["failing", "second"]
    assert len(failures) == 1
    assert isinstance(failures[0], HandlerFailure)
    assert failures[0].handler_name == "failing_handler"
    assert isinstance(failures[0].exception, RuntimeError)


async def test_handlers_run_sequentially_in_registration_order() -> None:
    bus = EventBus()
    order: list[int] = []

    for i in range(5):

        def handler(event: SampleEvent, i: int = i) -> None:
            order.append(i)

        bus.subscribe(SampleEvent, handler)

    await bus.publish(SampleEvent(value=0))

    assert order == [0, 1, 2, 3, 4]


class _FakeSyncSession:
    def __init__(self) -> None:
        self.info: dict[str, object] = {}


async def test_dispatch_pending_creates_tasks_and_clears_queue() -> None:
    bus = EventBus()
    received: list[SampleEvent] = []

    async def handler(event: SampleEvent) -> None:
        received.append(event)

    bus.subscribe(SampleEvent, handler)
    events_module.set_event_bus(bus)
    try:
        fake_session = _FakeSyncSession()
        fake_session.info[events_module._PENDING_EVENTS_KEY] = [SampleEvent(value=42)]

        events_module._dispatch_pending(fake_session)
        assert events_module._PENDING_EVENTS_KEY not in fake_session.info

        pending_tasks = list(events_module._background_tasks)
        for task in pending_tasks:
            await task

        assert received == [SampleEvent(value=42)]
    finally:
        events_module.set_event_bus(None)  # type: ignore[arg-type]


def test_clear_pending_removes_queue_without_dispatch() -> None:
    fake_session = _FakeSyncSession()
    fake_session.info[events_module._PENDING_EVENTS_KEY] = [SampleEvent(value=1)]

    events_module._clear_pending(fake_session)

    assert events_module._PENDING_EVENTS_KEY not in fake_session.info


@pytest.fixture(autouse=True)
def _reset_active_bus() -> None:
    yield
    events_module.set_event_bus(None)  # type: ignore[arg-type]
