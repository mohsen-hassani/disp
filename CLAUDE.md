# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

DISP: a self-hosted personal platform (FastAPI backbone + plug-in module contract + built-in auth
+ a Typer CLI). Built end-to-end from `TECHNICAL-SPEC.md`, a normative spec — if you're asked to
extend this project, that spec (and `docs/`) is the source of truth, not assumptions from other
FastAPI projects. See `README.md` for the architecture overview and `milestones/M00-M16` for the
full build history, including every resolved spec ambiguity and bug found along the way.

A web client (React PWA) is specified in `TECHNICAL-SPEC-WEB.md` and broken into an implementation
sequence at `milestones/client/M00-M12` — unlike the backend's `M00-M16`, those are prospective
(not-yet-built) briefs, not retrospective build logs. Exception: `milestones/client/M00` (backend
amendments) is implemented — see below.

## Commands

```
./dev up          # start local Postgres (docker-compose.test.yml — NOT docker-compose.yml)
./dev down
./dev migrate [branch]     # alembic upgrade head, all branches or one
./dev makemigration <branch> "<msg>"
./dev test [args...]       # pytest with coverage gates (needs Docker for testcontainers)
./dev lint                 # ruff check + ruff format --check + mypy src
./dev fmt                  # ruff format + ruff check --fix
./dev shell                # psql into the dev database
./dev seed                 # dev admin + three sample notes
./dev openapi               # write openapi.json to repo root
```

`docker-compose.yml` is the *production* stack (Postgres + api + worker + Traefik). Local dev only
ever needs `docker-compose.test.yml` (Postgres alone) — the app runs via `uv run` directly.

## Module boundaries (enforced by `tests/core/test_boundaries.py`, not just convention)

A module under `src/disp/modules/<domain>/` may **not**:
- import anything from another module (`disp.modules.<other>`)
- import `disp.core.app` at all
- import `disp.core.db` beyond `get_session`, `session_scope`, `Base`
- import `disp.core.auth` beyond its `__init__.py`'s public surface: `CurrentUser`, `Permission`,
  `can`, `current_user`, `grant`, `list_grants`, `readable_ids`, `require`, `require_admin`,
  `revoke` (wider than the spec's original 5-name list — see `milestones/M06-auth.md`)

Violating any of these fails the build, not a lint warning. See `docs/adding-a-module.md` for the
four-step recipe to add a new one.

## Settings panel JSON Schema (`GET /api/dashboard/manifest`)

Each `SettingsPanelSpec.schema_model` is serialized to JSON Schema on every manifest response
(`SettingsPanelOut.schema_`, aliased to the wire key `"schema"` — it can't be a literal `schema`
attribute, since that shadows `pydantic.BaseModel`'s own deprecated `.schema()` method and warns on
every construction) via `model_json_schema(mode="serialization")`, so a non-Python client can render
a settings form without a Pydantic-aware codegen step. A field is marked secret with
`Field(json_schema_extra={"x-secret": True})` — the marker key is `x-secret` end-to-end (not the
internal-only `"secret"` this used to be before a web client needed to see it), read back by
`settings_store._field_is_secret()`.

**Core-registered panels need a synthetic manifest entry.** A panel added via
`Registry.register_core_settings_panel()` (e.g. `core.notifier`, wired unconditionally in
`create_app()`) belongs to no discovered module — `disp.modules/*` discovery never sees `core` — so
`get_manifest()` cannot find it by walking `registry.modules` the way module-declared panels are
found. `dashboard.get_manifest()` therefore also appends a synthetic `domain="core"` module entry
for whatever's left in `registry.settings_panels` after the per-module loop. This means the
manifest's `modules` list always includes a `"core"` domain in addition to real modules — a test
asserting an exact domain set (e.g. `{"notes"}`) needs `{"notes", "core"}` instead; two pre-existing
tests hit this (`tests/cli/test_cli_commands.py`, `tests/core/test_plugin_proof.py`).

## Testing

- Real Postgres 16 via `testcontainers`, started once per session at `tests/conftest.py`
  **module-import time** (not in a fixture — must happen before anything imports
  `disp.core.scheduler`, which builds a process-wide `procrastinate.App` at import time).
- Per-test isolation via transaction rollback (SAVEPOINTs), except CLI tests
  (`tests/cli/`), which use a real-commit session — see that directory's `conftest.py` for why
  (sync CLI ↔ async app bridging needs a separate event loop, which can't share a savepoint-bound
  connection).
- **Coverage requires `concurrency = ["greenlet", "thread"]`** in `[tool.coverage.run]`
  (`pyproject.toml`). Without it, coverage.py silently drops most lines *after* an `await
  session.execute(...)` in SQLAlchemy-async code — a project-wide false "uncovered" reading, not a
  real gap. If coverage numbers look implausibly low for a well-tested async route, check this
  setting hasn't been reverted before writing more tests to "fix" it.
- **`./dev test` and a bare `pytest` invocation must behave identically.** `./dev` sources this
  repo's own `.env` (dev defaults, including `MYSTUFF_RATE_LIMIT_ENABLED=true`) into the shell
  before running pytest; a bare `pytest` never sees `.env` at all. `tests/conftest.py`'s required
  env vars are therefore **unconditional** overrides (`os.environ["KEY"] = ...`), not
  `setdefault` — a `setdefault` there previously caused real rate-limiting to leak into the whole
  suite only when run via `./dev test`, never when run directly.
- Gates: ≥85% overall, ≥95% on `src/disp/core/auth/`.

## Docker

Console scripts installed by `uv sync` (`alembic`, `disp-admin`, `procrastinate`, `disp`) get an
**absolute shebang** baked in at install time. The Dockerfile's builder stage must use the same
`WORKDIR` as the runtime stage (`/app`, not `/build`) or every console script breaks with
`exec: no such file or directory` after the multi-stage copy. Also build with
`uv sync --no-editable` — the default editable install links back to the builder stage's path,
breaking `import disp` at runtime. Both were caught by actually running the built image, not just
building it — always verify a Dockerfile change by running the image, not just building it.

The production image ships no `uv`/`./dev` (keeps it free of build tooling) — use the installed
console scripts directly for one-shot commands (`docker compose run --rm api alembic --name=core
upgrade head`, etc. — see `docs/operations.md`).
