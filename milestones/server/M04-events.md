# M4 — events.py

**Status:** Complete

**Scope:** `EventBus` (exact-type dispatch, sequential, exception-swallowing → `HandlerFailure`), `publish_after_commit` (listens on `session.sync_session`'s `after_commit`), core events (`UserCreated`, `UserLoggedIn`, `RefreshTokenReused`).

Covers TECHNICAL-SPEC.md §12 (Event bus).

---

## §12. Event bus

### 12.1 Semantics

```python
class EventBus:
    def subscribe(self, event_type: type[E], handler: Handler[E]) -> None
    async def publish(self, event: E) -> list[HandlerFailure]
```

- Events MUST be `@dataclass(frozen=True, slots=True)`.
- Dispatch matches the **exact** type. Subclass matching is not supported.
- Handlers may be sync or async; async handlers are awaited. Handlers run **sequentially** in registration order.
- A handler raising an exception MUST NOT prevent later handlers from running. The bus catches `Exception`, logs at `ERROR` with the traceback and the event type, and appends a `HandlerFailure(handler_name, exception)` to the returned list.
- `publish` never raises for handler failures. Callers that need strictness inspect the return value.
- Handlers MUST NOT receive the publisher's DB session. A handler needing DB access opens its own.

### 12.2 Transactional publication

```python
def publish_after_commit(session: AsyncSession, event: Any) -> None
```

Registers the event on the session's `after_commit` SQLAlchemy event so it is dispatched only if the transaction commits. Events published this way are dispatched via `asyncio.create_task`; failures are logged, never propagated. This is the recommended way for modules to emit domain events from request handlers.

### 12.3 Core events

`disp/core/events.py` MUST define and the platform MUST publish:

```python
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
```

## Implementation notes

- `publish_after_commit` needed a way to reach the process-wide `EventBus` without the exact spec signature `(session, event)` carrying a bus reference. Resolved with a module-level singleton set once at startup: `set_event_bus(bus)`, called from `create_app()`/`worker.py` (M10) when the `Platform`'s `EventBus` is constructed.
- Listens on `session.sync_session` (the real target of SQLAlchemy ORM session events) rather than the `AsyncSession` wrapper directly, since `AsyncSession` doesn't expose ORM events itself.
- A per-session pending-events list lives in `sync_session.info`, drained by the `after_commit` listener and cleared by an `after_rollback` listener (so a rolled-back transaction's events never fire — test case 37).
- `UserLoggedIn`/`UserCreated`/`RefreshTokenReused` are actually published from `auth/routes.py` (M6), which already existed by the time this was implemented in build order — see M6 notes.
