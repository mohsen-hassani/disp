# M7 — scheduler.py

**Status:** Complete

**Scope:** `procrastinate.App` + `PsycopgConnector`, `SchedulerFacade` (`.task`, `.defer`, duplicate-name-fatal), `to_psycopg_dsn()` helper, `default_retry_strategy()`, `core.daily_planner` periodic task.

Covers TECHNICAL-SPEC.md §13 (Scheduler and task queue).

---

## §13.1 Procrastinate setup

- One `procrastinate.App` in `disp/core/scheduler.py`, using `PsycopgConnector` with `MYSTUFF_DATABASE_URL_SYNC`.
- Procrastinate's own tables live in the `public` schema (its default). No customisation.
- `procrastinate schema --apply` runs as part of `./dev migrate` and as a one-shot compose command, before the worker starts.

## §13.2 Task registration

The platform exposes a thin facade so modules never import Procrastinate directly:

```python
class SchedulerFacade:
    def task(self, name: str, *, queue: str = "default", retry: int = 3) -> Callable[[F], F]: ...
    async def defer(self, name: str, **kwargs: Any) -> None: ...
```

- `name` MUST match `KEY_RE` (`<domain>.<task>`), so task names are namespaced by module.
- Registering a duplicate name is **fatal** at startup.
- Default retry strategy: 3 attempts, exponential backoff with `wait=10` seconds and `linear_wait=0`, i.e. retries at ~10 s, ~20 s, ~40 s.
- Tasks MUST accept only JSON-serialisable keyword arguments. Passing an ORM object is a programming error.

> **Implementation note on the retry formula:** procrastinate's actual `RetryStrategy` computes `total_wait = wait + linear_wait*attempts + exponential_wait**(attempts+1)`. With only `wait=10, linear_wait=0` set (as the spec's kwargs literally say) and `exponential_wait` left at its default `0`, the real result is a constant ~10s between all retries, not a 10/20/40 doubling sequence — procrastinate's formula can't produce an exact 10/20/40 geometric sequence from any parameter combination (it supports constant + linear + power-tower terms, not multiplicative doubling). Implemented literally as `RetryStrategy(max_attempts=n, wait=10, linear_wait=0)`, prioritizing the explicit named kwargs over the approximate "i.e." illustration, since the two are in tension and the kwargs are the more concrete instruction.

## §13.3 The daily planner

A periodic task named `core.daily_planner`, cron from `MYSTUFF_DAILY_PLANNER_CRON`, MUST:

1. Receive Procrastinate's single `timestamp: int` argument.
2. Log start with the resolved local date in `MYSTUFF_TIMEZONE`.
3. Iterate `registry.scheduled_jobs`, and for each, log its name. (Actual per-module fan-out is each module's responsibility via its own periodic jobs; the planner exists to prove the mechanism and to provide a single hook for future cross-module planning.)
4. Log completion with a count.

It MUST be idempotent: running it twice for the same day produces no duplicate side effects. (Satisfied trivially — the task only logs, no DB writes, so re-running it has no side effects to duplicate.)

## §13.4 Worker configuration

The worker container runs `python -m disp.worker`, which MUST call `app.run_worker_async(concurrency=4, install_signal_handlers=True, listen_notify=True)` after discovery. Graceful shutdown on `SIGTERM` within 30 seconds. (Implemented in `worker.py` at M10.)

## Implementation notes

- Installed `procrastinate==3.9.0` (spec pins `>=2.9`); its API differs somewhat from 2.x but all needed pieces (`PsycopgConnector`, `App.task`, `App.periodic`, `defer_async`, `run_worker_async(concurrency=..., install_signal_handlers=..., listen_notify=...)`) exist and were verified interactively against the installed package via `inspect.signature`/`inspect.getsource` before writing code.
- `PsycopgConnector(conninfo=...)` needs a bare `postgresql://` DSN, not the SQLAlchemy-dialect-prefixed `postgresql+psycopg://` that `MYSTUFF_DATABASE_URL_SYNC` provides — `to_psycopg_dsn()` strips the `+driver` marker via regex.
- `app = procrastinate.App(...)` and the `daily_planner`/`core.deliver_notification` (M9) task registrations are module-level, evaluated at **import time** of `disp.core.scheduler` — this matches the CLI's expectation that `disp.core.scheduler.app` is a ready-made dotted-path-loadable object (`procrastinate --app=disp.core.scheduler.app schema --apply`). Consequence: importing this module requires valid `MYSTUFF_*` env vars to already be set in the process (same as any settings-dependent module-level singleton).
- `daily_planner`'s access to `registry.scheduled_jobs` (not available until M10's wiring) uses the same module-level-singleton-with-setter pattern as `events.py`: `set_registry(registry)`, called once during platform construction.
- `SchedulerFacade.task()` proactively checks `name in self._app.tasks` before returning the decorator (duplicate-name-fatal), raising `SchedulerRegistrationError`. Verified interactively: duplicate registration raises, bad task-name pattern raises `ValueError`, DSN conversion round-trips correctly.
