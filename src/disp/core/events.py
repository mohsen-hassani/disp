import asyncio
import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar
from uuid import UUID

import structlog
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

E = TypeVar("E")

Handler = Callable[[E], None] | Callable[[E], Awaitable[None]]

_PENDING_EVENTS_KEY = "_disp_pending_events"
_LISTENERS_REGISTERED_KEY = "_disp_after_commit_registered"

_background_tasks: set[asyncio.Task[None]] = set()


@dataclass(frozen=True, slots=True)
class HandlerFailure:
    handler_name: str
    exception: BaseException


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[Any], list[Callable[[Any], Any]]] = defaultdict(list)

    def subscribe(self, event_type: type[E], handler: Handler[E]) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: E) -> list[HandlerFailure]:
        failures: list[HandlerFailure] = []
        for handler in self._handlers.get(type(event), []):
            handler_name = getattr(handler, "__name__", repr(handler))
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # handler failures must not abort dispatch to later handlers
                logger.error(
                    "event_handler_failed",
                    handler=handler_name,
                    event_type=type(event).__name__,
                    exc_info=exc,
                )
                failures.append(HandlerFailure(handler_name=handler_name, exception=exc))
        return failures


_active_bus: EventBus | None = None


def set_event_bus(bus: EventBus) -> None:
    """Bind the process-wide EventBus that `publish_after_commit` dispatches through."""
    global _active_bus
    _active_bus = bus


async def _publish_and_log(bus: EventBus, event: Any) -> None:
    try:
        await bus.publish(event)
    except Exception as exc:  # fire-and-forget dispatch must never raise
        logger.error(
            "publish_after_commit_failed",
            event_type=type(event).__name__,
            exc_info=exc,
        )


def _dispatch_pending(sync_session: Any) -> None:
    pending: list[Any] = sync_session.info.pop(_PENDING_EVENTS_KEY, [])
    bus = _active_bus
    if bus is None or not pending:
        return
    loop = asyncio.get_running_loop()
    for event in pending:
        task = loop.create_task(_publish_and_log(bus, event))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)


def _clear_pending(sync_session: Any) -> None:
    sync_session.info.pop(_PENDING_EVENTS_KEY, None)


def publish_after_commit(session: AsyncSession, event: Any) -> None:
    """Dispatch `event` on the bound EventBus only if `session`'s transaction commits."""
    sync_session = session.sync_session
    pending: list[Any] = sync_session.info.setdefault(_PENDING_EVENTS_KEY, [])
    pending.append(event)

    if not sync_session.info.get(_LISTENERS_REGISTERED_KEY):
        sync_session.info[_LISTENERS_REGISTERED_KEY] = True
        sa_event.listens_for(sync_session, "after_commit")(_dispatch_pending)
        sa_event.listens_for(sync_session, "after_rollback")(_clear_pending)


@dataclass(frozen=True, slots=True)
class UserCreated:
    user_id: UUID
    email: str


@dataclass(frozen=True, slots=True)
class UserLoggedIn:
    user_id: UUID
    auth_method: str
    ip_address: str | None


@dataclass(frozen=True, slots=True)
class RefreshTokenReused:
    user_id: UUID
    family_id: UUID
