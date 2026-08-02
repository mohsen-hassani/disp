# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

DISP: a self-hosted personal platform (FastAPI backbone + plug-in module contract + built-in auth
+ a Typer CLI). Built end-to-end from `TECHNICAL-SPEC.md`, a normative spec — if you're asked to
extend this project, that spec (and `docs/`) is the source of truth, not assumptions from other
FastAPI projects. See `README.md` for the architecture overview and `milestones/M00-M16` for the
full build history, including every resolved spec ambiguity and bug found along the way.

A web client (React PWA) is specified in `TECHNICAL-SPEC-WEB.md` and broken into an implementation
sequence at `milestones/client/M00-M12` — unlike the backend's `M00-M16`, those started as
prospective (not-yet-built) briefs, not retrospective build logs. Exception: `milestones/client/
M00-M11` are now implemented (see `README.md`'s "Web client" section for what each covers, and
"Web client" below for testing/dev notes specific to it); only `M12` (production Docker image +
Traefik routing) remains prospective.

Two modules ship: `notes` (the demo that exercises the contract) and `plants` (plant care
schedules). `plants` was built after the spec rather than from it, so it documents itself —
`src/disp/modules/plants/TECHNICAL-SPEC.md` is the complete as-built reference (data model,
scheduling invariants, API, photo storage, rationale for every decision) and is the source of truth
before changing anything under `src/disp/modules/plants/` or the `/plants` client screens. Its
`README.md` is the short orientation. **The load-bearing rule: completing a care action reschedules
from the completion date, not the due date** (done on the 3rd for a 15-day cycle → next due the
18th, not the 16th), and due/overdue state is *derived* at read time, never stored.

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
asserting an exact domain set needs `{"notes", "plants", "core"}`, not just the real module domains;
two tests hit this (`tests/cli/test_cli_commands.py`, `tests/core/test_plugin_proof.py`).

## Adding a module: branch registration is one line now

A module's Alembic branch used to need edits in `src/disp/core/migrations/env.py` (a hardcoded
`BRANCH_MODELS` dict) and in `./dev` (a hardcoded module allow-list) — which contradicted the
platform's own "adding a module requires zero `core/` edits" promise that
`tests/core/test_plugin_proof.py` asserts. Both are now derived: `env.py`'s `_models_module()`
resolves `disp.modules.<branch>.models` by convention, and `./dev migrate` upgrades every module
shipping a `migrations/versions/` directory. **A new module needs only its `alembic.ini` section**,
plus one line each in `tests/conftest.py` and `docker-compose.e2e.yml` (both still enumerate
branches explicitly). Don't reintroduce a hardcoded module list in either derived spot.

## `plants` gotchas (full reasoning in that module's `TECHNICAL-SPEC.md`)

- **Plant photos are files on a volume, not rows.** `DISP_PLANTS_MEDIA_ROOT`, mounted as
  `media:/data/media` in `docker-compose.yml`. `pg_dump` therefore does **not** contain them, and a
  database-only restore fails *gracefully* (`404 plants.no_image`) which makes the gap easy to miss
  — `docs/operations.md` has the volume backup cron.
- **The media root default is a *relative* path** (`var/media/plants`). Anything comparing paths
  under it must compare resolved-to-resolved: a bug where `write_image` deleted the file it had just
  written survived the whole unit suite because pytest's `tmp_path` is absolute and already
  resolved, and only showed up running the real server. `test_image_survives_a_relative_media_root`
  pins it. More generally: when behaviour depends on a config's *shape*, test the shipped default's
  shape, not just a convenient one.
- **`/due` and `/calendar` must stay declared above `/{plant_id}` in `router.py`.** FastAPI matches
  in declaration order; reordering makes `GET /api/plants/due` try to parse `"due"` as a UUID (422).

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
  repo's own `.env` (dev defaults, including `DISP_RATE_LIMIT_ENABLED=true`) into the shell
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

## Web client (`clients/web/`)

Two test layers, both run from `clients/web/`: `pnpm test` (Vitest — unit/component, real coverage
gates) and `pnpm test:e2e` (Playwright — full stack against a real backend). See `README.md`'s "Web
client" section for the exact commands.

- **Any UI change (new screen, new component, or edit to an existing one) follows
  `docs/design-system/`.** It's the "DISP Design System" project pulled from claude.ai/design —
  components by category (`components/{core,forms,feedback,navigation,overlay,data}/`), design
  tokens (`tokens/*.css`: color, type, spacing, radius, motion), and 12 foundation specimens
  (`guidelines/*.card.html`); `docs/design-system/readme.md` has the full rationale (tone/copy
  rules, color/spacing/motion specs, open decisions). **Read `readme.md`'s "Caveats" section
  first**: it was authored from a written product brief only, with no real DISP codebase
  attached, so it's a reference to reconcile against, not ground truth to copy verbatim — and it
  uses plain inline-styled `.jsx` + raw CSS custom properties, not this repo's actual
  Tailwind/Radix stack (`clients/web/tailwind.config.ts`, `@radix-ui/react-*` in
  `clients/web/package.json`). Translate its tokens and component APIs (variant names, sizes,
  states) into this codebase's real conventions — Tailwind utility classes and
  `src/components/ui/`-style Radix wrappers — rather than importing its files or inline-style
  objects directly. If a design decision here conflicts with what's already shipped in
  `clients/web/src/components/`, treat the shipped code as current ground truth and flag the
  conflict rather than silently overriding it.
- **Coverage gates are enforced**, not aspirational (`vitest.config.ts`'s `coverage.thresholds`):
  ≥80% lines overall, ≥95% on `src/auth/` and `src/components/schema-form/` (glob-keyed
  per-directory thresholds, same mechanism as the backend's `≥85%/≥95%` split). A number that looks
  implausibly low for well-tested code is a config problem to find, not a target to lower.
- **`docker-compose.e2e.yml` is layered on `docker-compose.yml`**, not standalone like
  `docker-compose.test.yml` — run as `docker compose -f docker-compose.yml -f
  docker-compose.e2e.yml up`, never alone (its own header comment has the full rationale). It
  overrides `DISP_DATABASE_URL` to point at the compose-network `postgres` (not whatever
  `localhost` URL is in the developer's own `.env`), runs a one-shot `migrate` service (Alembic +
  Procrastinate schema + a deterministic seeded admin via `DISP_SEED_PASSWORD`) before `api`/
  `worker` start, exposes the API directly on `localhost:8000`, and disables Traefik via a
  `profiles: ["disabled"]` override (no real domain/ACME email exists in an e2e run). Requires
  `POSTGRES_PASSWORD` set on the invoking shell — `docker-compose.yml`'s own `:?required` has no
  default. Run `... down -v` between runs: the seeded admin refuses to be created twice.
- **Same-origin routing, ahead of `M12`.** The client requires the API to be same-origin (§2.1) —
  in production that's Traefik path-routing (§24.4), not built yet. Until then, `vite.config.ts`
  defines the same proxy shape under both `server.proxy` (used by `pnpm dev`) and `preview.proxy`
  (used by `pnpm preview`, what Playwright's `webServer` runs) — Vite doesn't share config between
  the two — forwarding `/api`, `/health`, and `/openapi.json` to `localhost:8000`. This is a
  dev/preview-only stand-in meant to be replaced by real Traefik routing once `M12` ships the
  `web` container, not extended.
- **MSW (`tests/mocks/`) needs jsdom's origin pinned.** `vitest.config.ts` sets
  `environmentOptions.jsdom.url: 'http://localhost/'` — MSW resolves a handler's relative URL
  pattern against `document.location`, and jsdom's own default origin (`http://localhost:3000`)
  doesn't match the `http://localhost` baseUrl every test file's `client.setConfig(...)` already
  standardizes on (see `tests/unit/api/client.test.ts`). Without this, MSW handlers silently never
  match and every request 404s.
- **A route's `beforeLoad` must `ensureQueryData`, never bare `getQueryData`, for anything a
  parent route's `loader` populates.** TanStack Router runs every matched route's `beforeLoad`
  before any route's `loader` — so on a fresh/direct navigation (not a client-side `<Link>` click
  from an already-loaded page), a child's `beforeLoad` can run before the parent loader that fills
  the cache it wants to read. Caught live by the e2e suite: `/settings/$domain`'s domain-validity
  check 404'd on a direct load despite the domain being real, because it read the manifest cache
  with `getQueryData` (no fetch) instead of `ensureQueryData` (fetches-or-waits, and de-dupes
  against the parent's identical query). If a `beforeLoad` reads a query another route's `loader`
  is responsible for populating, it must `await ensureQueryData` that same query itself.
