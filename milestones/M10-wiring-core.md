# M10 — Wiring core (platform, registry, app, health, dashboard, main, worker)

**Status:** Complete

**Scope:** `platform.py` (`Platform` dataclass), `registry.py` (`Registry.discover()` + `Registry.wire()`), `app.py` (`create_app()`), `health.py`, `dashboard.py`, `main.py`, `worker.py`, plus `tests/core/test_registry.py` against `tests/fixtures_modules/{hello,broken_manifest,cyclic_a,cyclic_b}`.

Covers TECHNICAL-SPEC.md §9 (Module registry and startup), §16 (Dashboard API), §17.1/§17.2/§17.6/§17.7 (HTTP API conventions not already covered in M1), and the `GET /health`/`GET /health/live` part of §20.

---

## §9.1 Discovery algorithm

`Registry.discover()` MUST execute exactly these steps:

1. Enumerate candidate packages with `pkgutil.iter_modules(disp.modules.__path__)`. Order is not guaranteed; sort names alphabetically for determinism.
2. If `MYSTUFF_MODULES` is non-empty, filter to that allow-list. A named module that does not exist is a **fatal** error.
3. For each candidate: `importlib.import_module(f"disp.modules.{name}")`.
   - `ImportError` → fatal, with the original traceback.
4. Retrieve `get_module`. Missing attribute or non-callable → fatal.
5. Call it. The result MUST have a `manifest` attribute that is a `ModuleManifest` instance → otherwise fatal.
6. Assert `manifest.domain == name`. Mismatch → fatal.
7. Collect all manifests, then validate globally:
   - duplicate `domain` → fatal;
   - duplicate tile `key`, settings-panel `key`, scheduled-job `name`, or notification-type `key` across modules → fatal;
   - a `dependencies` entry not present among discovered domains → fatal.
8. Topologically sort by `dependencies` (Kahn's algorithm). A cycle → fatal, and the error message MUST name the modules in the cycle.
9. Return the ordered list.

"Fatal" means: log at `CRITICAL` with a message naming the offending module and the specific rule violated, then raise `ModuleRegistrationError`. In `main.py` this propagates and the process exits non-zero. There is **no** partial-loading mode.

## §9.2 Wiring

For each module, in dependency order, `Registry.wire(app, platform)` MUST:

1. Call `module.register(platform)`.
2. If `module.api_router()` returns a router, include it with `prefix=f"/api/{domain}"` and `tags=[domain]`.
3. For each `ScheduledJobSpec`, look up the task registered under that name in the scheduler; a missing task is **fatal**. Register it as periodic with the spec's cron.
4. Index tiles, settings panels, and notification types into read-only dictionaries keyed by their `key`.

`register()` MUST NOT perform I/O. Database work belongs in request handlers or tasks.

> **Resolved gap:** the spec doesn't say how `core`'s own built-ins (the `core.daily_planner` scheduled job from M7, the `core.notifier` settings panel from M9) get indexed into these same dictionaries, since step 4 only describes indexing for modules coming out of `discover()`. Resolved by having `create_app()`/`Registry` register these two directly against the same internal structures, alongside (not through) module discovery/wiring.

## §9.3 Application factory

`create_app()` MUST, in order:

1. Load settings; configure logging (§20).
2. Create the async engine and session maker.
3. Construct `EventBus`, `SettingsStore`, `SchedulerFacade`, `NotifierFacade`, then the `Platform`.
4. Build the `FastAPI` instance with `title="MyStuff"`, `version=__version__`, `openapi_url="/openapi.json"`, `docs_url="/docs"` (only when `MYSTUFF_ENV != "production"`; otherwise `None`).
5. Install middleware in this order (outermost first): `RequestIdMiddleware`, `CORSMiddleware`, `SlowAPIMiddleware`.
6. Register exception handlers (§17.4 — already implemented in M1's `errors.py`).
7. Mount core routers: `/health`, `/api/auth`, `/api/dashboard`, `/api/settings`.
8. Run `Registry.discover()` and `Registry.wire()`.
9. Register a lifespan handler that opens the Procrastinate connector on startup and closes it, plus the DB engine, on shutdown.

The registry MUST be attached as `app.state.registry` and the platform as `app.state.platform`.

**Middleware ordering note:** Starlette's `add_middleware()` makes the *last*-added middleware the outermost. To get "outermost first: RequestIdMiddleware, CORSMiddleware, SlowAPIMiddleware", call `add_middleware()` in the reverse order: `SlowAPIMiddleware` first, then `CORSMiddleware`, then `RequestIdMiddleware` last.

## §9.4 Worker entrypoint

`src/disp/worker.py` MUST perform steps 1–3 and 8 of §9.3 (settings, logging, engine, platform, discovery, wiring of tasks and event handlers) **without** constructing a FastAPI app, then hand control to Procrastinate's worker. This guarantees module tasks and event subscriptions exist in the worker process.

Per §13.4: `python -m disp.worker` MUST call `app.run_worker_async(concurrency=4, install_signal_handlers=True, listen_notify=True)` after discovery. Graceful shutdown on `SIGTERM` within 30 seconds.

## §16. Dashboard API

### 16.1 `GET /api/dashboard/manifest`

Authenticated. Returns the full capability index. Response:

```json
{
  "platform_version": "1.0.0",
  "modules": [
    {
      "domain": "notes",
      "name": "Notes",
      "version": "1.0.0",
      "description": "Quick notes",
      "tiles": [
        {"key":"notes.latest","title":"Latest notes","description":null,
         "size":"medium","refresh_seconds":300,"order":100}
      ],
      "settings_panels": [],
      "notification_types": [
        {"key":"notes.reminder","title":"Note reminder",
         "description":null,"default_enabled":true}
      ]
    }
  ]
}
```

`scheduled_jobs` are **not** exposed — they are internal.

### 16.2 `GET /api/dashboard/tiles`

Authenticated. Renders every registered tile for the calling user and returns `{"tiles": [TileData, ...]}` ordered by `TileSpec.order` then `key`.

A tile provider that raises MUST NOT fail the whole response. The platform catches the exception, logs it at `ERROR` with the tile key, and substitutes:

```json
{"key":"notes.latest","title":"Latest notes","count":null,"items":[],
 "actions":[],"empty_text":"This tile failed to load","generated_at":"..."}
```

A provider MUST be given at most 3 seconds (`asyncio.timeout`); a timeout is treated as a failure.

### 16.3 `GET /api/dashboard/tiles/{tile_key}`

Renders one tile. `404 dashboard.tile_not_found` for an unknown key. Errors here **do** propagate as `500`, since the caller asked for that specific tile.

## §17.1 Paths and versioning

- All application routes live under `/api/`. Module routes are `/api/{domain}/...`.
- No URL version segment. The OpenAPI document version tracks `__version__`.
- Resource collections are plural nouns. Sub-resources nest at most one level.
- Trailing slashes are not used; FastAPI's `redirect_slashes` MUST be disabled.

## §17.2 Status codes

| Code | Use |
|---|---|
| `200` | Successful read or update returning a body |
| `201` | Resource created; `Location` header set |
| `204` | Success with no body (delete, logout) |
| `400` | Semantically invalid request that is not a schema violation |
| `401` | Missing or invalid authentication |
| `403` | Authenticated but not permitted |
| `404` | Not found, or found but not visible to the caller |
| `409` | Conflict with current state |
| `410` | Gone (expired invite) |
| `422` | Schema validation failure |
| `429` | Rate limited; `Retry-After` header set |
| `500` | Unhandled server error |

A resource that exists but that the caller may not read MUST return `404`, not `403`, to avoid existence disclosure. `403` is reserved for cases where the caller can already see the resource but lacks the specific permission (e.g. write on a shared item).

## §17.6 CORS, headers, rate limiting

- CORS is enabled only when `MYSTUFF_CORS_ORIGINS` is non-empty; `allow_credentials=True`, methods `GET, POST, PATCH, DELETE, OPTIONS`, headers `Authorization, Content-Type, X-Requested-With`.
- Every response carries `X-Request-ID`.
- Rate limits (`slowapi`, keyed by client IP unless noted), applied when `MYSTUFF_RATE_LIMIT_ENABLED`:

| Endpoint | Limit |
|---|---|
| `POST /api/auth/login` | 10/minute per IP **and** 5/minute per submitted email |
| `POST /api/auth/refresh` | 60/minute per IP |
| `POST /api/auth/accept-invite` | 10/hour per IP |
| `POST /api/auth/tokens` | 20/hour per user |
| `POST /api/auth/password` | 5/hour per user |
| all other routes | 300/minute per IP |

Exceeding a limit returns `429` with `Retry-After`.

(The auth-specific limits above were already implemented in M6's `auth/routes.py` using the shared `limiter` from `errors.py`. This milestone's job is the *default* 300/minute-per-IP catch-all, via `Limiter(default_limits=["300/minute"])`, and wiring `SlowAPIMiddleware` + `app.state.limiter` in `create_app()`.)

## §17.7 OpenAPI

- Every route MUST declare `response_model`, `status_code`, `summary`, and a `responses` dict documenting each non-2xx status it can return.
- Every route MUST carry exactly one tag: its domain, or `auth`, `dashboard`, `settings`, `health`.
- `operation_id` MUST be set explicitly as `{tag}_{action}` (e.g. `notes_list`, `auth_login`) so generated clients have stable method names.

## §20 (health endpoints, the part not covered in M1)

**`GET /health`** (unauthenticated) returns:

```json
{"status":"ok","version":"1.0.0","database":"ok",
 "modules":["notes"],"worker_last_seen":"2026-07-24T09:00:00Z"}
```

`status` is `ok` only when the database responds to `SELECT 1` within 2 seconds. `worker_last_seen` is derived from the most recent successful Procrastinate job; `null` is not an error. Degraded → `503` with `status: "degraded"`.

`GET /health/live` returns `200 {"status":"ok"}` without touching the database.

## Registry test fixtures needed (write alongside `test_registry.py`)

`tests/fixtures_modules/{hello,broken_manifest,cyclic_a,cyclic_b}` — the `hello` fixture is given complete in Appendix B.5 of the spec:

```python
# tests/fixtures_modules/hello/__init__.py
from datetime import datetime
from fastapi import APIRouter
from disp.core.contract import (
    ModuleManifest,
    PlatformModule,
    TileData,
    TileSpec,
    TileSize,
    TileContext,
)

MANIFEST = ModuleManifest(
    domain="hello",
    name="Hello",
    version="1.0.0",
    tiles=(TileSpec(key="hello.greeting", title="Hello", size=TileSize.SMALL),),
)


async def _greeting(ctx: TileContext) -> TileData:
    return TileData(
        key="hello.greeting",
        title="Hello",
        count=1,
        items=[],
        actions=[],
        empty_text="hi",
        generated_at=ctx.now,
    )


class HelloModule:
    manifest = MANIFEST

    def register(self, platform) -> None:
        return None

    def api_router(self) -> APIRouter | None:
        return None

    def tile_provider(self, key: str):
        return _greeting if key == "hello.greeting" else None


def get_module() -> PlatformModule:
    return HelloModule()
```

`broken_manifest` and `cyclic_a`/`cyclic_b` are not given verbatim by the spec — write minimal modules exercising, respectively: a domain/package-name mismatch (test case 30) and a two-module dependency cycle (test case 33).

## Implementation notes

- **`Registry` indexing gap resolved.** §9.2 says settings panels are indexed "keyed by their key" (e.g. `"core.notifier"`), but the generic settings HTTP router (M8) needs to look up a panel by bare domain (e.g. `"core"`). Kept `Registry.settings_panels` keyed by full key (satisfying the literal instruction and duplicate-key detection), and added a derived accessor `settings_panel_for_domain(domain)` that strips the domain prefix — used by `settings_store.py` instead of indexing directly.
- **Core built-ins.** `core.daily_planner` and the `core.notifier` settings panel aren't discovered via `disp.modules`, so `create_app()`/`worker.py` register them directly against the same `Registry` structures via `register_core_scheduled_job()`/`register_core_settings_panel()`, right after `registry.wire()` — the gap identified back at M7/M9.
- **`Registry.wire(app, platform)` made `app` optional.** The worker process (§9.4) wires tasks/event handlers but never serves HTTP, so `wire()` accepts `app: FastAPI | None` and simply skips router inclusion when `None` — needed because the spec's `wire(app, platform)` signature is shared between both entrypoints.
- **Middleware ordering verified empirically.** Starlette's `add_middleware()` makes the *last*-added middleware the outermost, so `create_app()` calls it in reverse (`SlowAPIMiddleware`, then `CORSMiddleware`, then `RequestIdMiddleware`) to produce the required outermost-first order. Confirmed via `app.user_middleware` inspection: `['RequestIdMiddleware', 'CORSMiddleware', 'SlowAPIMiddleware']`.
- **Real bug found and fixed:** `_wait_for_database`'s retry loop (§5.3's "unreachable after 5 retries with 2-second backoff") only caught `SQLAlchemyError`, but asyncpg raises a bare `OSError` on connection refusal (confirmed interactively — SQLAlchemy does not wrap it at the `engine.connect()` pool-checkout stage). The loop was failing on the very first attempt without ever retrying. Fixed by catching `(SQLAlchemyError, OSError)`; verified the retry loop now takes the full ~9 seconds (5 attempts, 2s backoff) before raising, with `CRITICAL`-level logging on final failure. Applied the same fix to `health.py`'s DB check functions, which had the identical gap.
- **Settings-panel schema limitation.** `SettingsPanelSpec.schema_model` (a `type[BaseModel]`) can't be serialized directly into the `GET /api/dashboard/manifest` response, so a dedicated `SettingsPanelOut` (key/title/description/scope only) is used for that one field instead of echoing the manifest's tuple verbatim.
- **Verification performed:** `create_app()` constructs successfully and mounts all 16 routes (19 operations across health/auth/dashboard/settings) with unique `operation_id`s and exactly one tag each, confirmed via the generated OpenAPI schema; `MYSTUFF_ENV=production` correctly disables `docs_url`/`redoc_url` while keeping `openapi_url`; the `hello` fixture module was path-injected and correctly appeared in `registry.modules`/`registry.tiles` with **zero edits to `src/disp/core/`** (the actual §22.4 plug-in-proof property, informally confirmed here — the formal test with `git diff` assertion is written at M15); `tests/core/test_registry.py` (8 tests) covers discovery success, allow-list restriction, unknown-module-in-allow-list fatal, domain/package mismatch fatal, dependency-cycle fatal (naming both modules), missing-dependency fatal, and tile wiring/rendering. Test cases 29 (real `notes` module) and 31 (duplicate tile keys — see note below) are deferred to M15.
- **Test case 31 deferred.** "Duplicate tile keys across two fixture modules are fatal" turns out to be unreachable through normal `ModuleManifest(...)` construction: the cross-field validator (M3) already forces every tile key to start with `f"{domain}."`, and domain is forced to equal the (unique) package name — so two *validly constructed* discovered modules can never produce a colliding tile key. Exercising this fatal path for real requires deliberately bypassing the Pydantic validator (e.g. `ModuleManifest.model_construct(...)`) in a dedicated fixture, which is a small enough addition to fold into M15's full test sweep rather than build here.
- Full suite: 23/23 tests passing, `ruff check`/`ruff format --check` clean, `mypy src` clean (all forward-reference placeholders from M3/M4/M7/M8/M9 for `disp.core.platform`/`disp.core.registry` are now fully resolved).
