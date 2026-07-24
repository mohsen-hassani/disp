# Adding a module

A module is a self-contained package under `src/disp/modules/<domain>/` that plugs into the
platform without editing anything under `src/disp/core/`. `tests/fixtures_modules/hello/` and
`tests/core/test_plugin_proof.py` prove this mechanically: that test copies a module in, restarts
the app factory, and asserts (via `git status`) that zero files under `core/` changed.

## The four steps

### 1. Write the manifest

Every module exposes a module-level `MANIFEST: ModuleManifest` describing what it contributes —
tiles, settings panels, scheduled jobs, notification types — and a `get_module()` factory that
returns an object implementing the `PlatformModule` protocol (`manifest`, `register()`,
`api_router()`, `tile_provider()`).

```python
# src/disp/modules/hello/__init__.py
from fastapi import APIRouter

from disp.core.contract import (
    ModuleManifest,
    PlatformModule,
    TileContext,
    TileData,
    TileSize,
    TileSpec,
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

    def register(self, platform: "Platform") -> None:
        return None  # no event subscriptions, no scheduled tasks

    def api_router(self) -> APIRouter | None:
        return None  # no HTTP routes

    def tile_provider(self, key: str) -> object:
        return _greeting if key == "hello.greeting" else None


def get_module() -> PlatformModule:
    return HelloModule()
```

`manifest.domain` **must** equal the package's own directory name (`hello`), or discovery fails
fatally at startup (§9.1 step 6). Every `key`/`name` a manifest declares (tile keys, settings
panel keys, scheduled job names, notification type keys) must be prefixed `<domain>.` — Pydantic
validates this automatically (`ModuleManifest._validate_key_prefixes`).

### 2. Add your own schema and migration branch

A module that persists anything owns its own Postgres **schema** (not `core`) and its own Alembic
**branch**, so its migrations never touch another module's tables. Add a section to `alembic.ini`:

```ini
[yourmodule]
script_location = src/disp/modules/yourmodule/migrations
version_locations = src/disp/modules/yourmodule/migrations/versions
version_table = alembic_version_yourmodule
version_table_schema = yourmodule
```

then `./dev makemigration yourmodule "initial schema"`. Models inherit from the shared
`disp.core.db.Base` (this is the *only* name from `disp.core.db` a module may import besides
`get_session`/`session_scope` — see §4 below) so `alembic`'s `include_object` filter can find them,
but must **never** declare a foreign key into another schema (see `notes.models.Note.user_id`,
a bare UUID column with no FK to `core.users`, with a comment explaining why).

### 3. Wire in your business logic

- HTTP routes: return an `APIRouter` from `api_router()`; the registry mounts it at
  `/api/<domain>`, tagged `<domain>`.
- Background tasks: register them inside `register(platform)` via
  `platform.scheduler.task("<domain>.<name>")` (never import Procrastinate directly). Declare
  periodic ones in the manifest's `scheduled_jobs`.
- Dashboard tiles: implement `tile_provider(key)`, returning an
  `async def(ctx: TileContext) -> TileData` for each tile key in your manifest. A provider that
  raises or times out (3s) degrades to a fallback tile — it never 500s the whole dashboard.
- Events: subscribe in `register(platform)` via `platform.events.subscribe(EventType, handler)`.

See `src/disp/modules/notes/` for a complete, non-trivial example exercising all of the above
(HTTP CRUD, a scheduled cleanup task, a dashboard tile, and an event subscription).

### 4. Respect the module boundaries

These are enforced automatically by `tests/core/test_boundaries.py`, not just documented —
violating them fails the build, not a style check:

- **No cross-module imports.** A module under `disp/modules/X/` may not import anything from
  `disp/modules/Y/`.
- **`disp.core.db`: only `get_session`, `session_scope`, and `Base`.** Not `create_engine` or
  `create_session_maker` — those would bypass the platform's connection pooling.
- **`disp.core.auth`: only the names actually exported from `disp.core.auth.__init__`** — never a
  submodule import like `from disp.core.auth.routes import ...`. The exported surface is
  `CurrentUser`, `Permission`, `can`, `current_user`, `grant`, `list_grants`, `readable_ids`,
  `require`, `require_admin`, `revoke` — the full ACL API plus authentication, but none of the
  session/token/password/invite internals. (This is wider than the spec's original literal
  five-name enumeration; see `milestones/M06-auth.md` for why it was expanded — the short version
  is that §18.3 requires modules to call `grant()`/`readable_ids()` directly, and ACL isn't part
  of the authentication surface an OIDC migration would ever touch.)
- **Never `import disp.core.app`.** A module has no business knowing about the FastAPI app object.
- **No I/O in `register()`.** Database work belongs in request handlers or tasks, not module
  registration.

## Verifying your module needs zero core/ changes

The pattern `tests/core/test_plugin_proof.py` uses works for any new module too: restrict
discovery to just your module (`MYSTUFF_MODULES=yourmodule`), build the app, and confirm
`git status --porcelain -- src/disp/core` is empty. If it isn't, something in your module reached
outside the boundaries above.
