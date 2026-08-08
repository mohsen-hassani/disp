# DISP

A self-hosted personal platform: a FastAPI backbone with a plug-in module contract, built-in auth
(JWT access tokens + refresh-token rotation with reuse detection + personal access tokens), and a
Typer CLI (`disp`). Ships with two modules: `notes`, a demo that exercises the full plug-in surface
(HTTP CRUD, a dashboard tile, a scheduled cleanup task, an event subscription) so you can see what
a real module looks like before writing your own, and `plants`, a plant care tracker (recurring
watering/feeding schedules, a month calendar, photo uploads, a daily reminder digest).

## Quickstart

Requires [`uv`](https://docs.astral.sh/uv/) and Docker (for local Postgres).

```sh
git clone <this repo> disp && cd disp
uv sync

cp .env.example .env
# Edit .env: generate real secrets —
#   python -c "import secrets; print(secrets.token_urlsafe(48))"          # DISP_JWT_SECRET
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # DISP_SETTINGS_KEY
# For local dev, DISP_COOKIE_SECURE=false and DISP_ENV=development are fine as shipped.

./dev up          # starts a local Postgres 16 container
./dev migrate     # applies all Alembic branches + the Procrastinate schema
./dev seed        # creates a dev admin user and three sample notes

uv run uvicorn disp.main:app --reload   # API on http://localhost:8000
uv run python -m disp.worker            # in a second terminal: background task worker

uv run disp login --server http://localhost:8000   # prompts for the admin credentials ./dev seed printed
uv run disp notes list
```

Run `./dev test` (full suite, needs Docker for testcontainers) and `./dev lint` before committing.

## Web client

A React PWA at `clients/web/` consumes this API — see
[`TECHNICAL-SPEC-WEB.md`](TECHNICAL-SPEC-WEB.md) for the full spec and
[`milestones/client/`](milestones/client/) for its build sequence. **All of `M00`–`M12` are
implemented** (backend amendments, the generated API client, browser auth, routing/shell, the
dashboard's generic tile rendering, generic settings rendering, the account/API-tokens/admin-invites
screens, the bespoke notes screens with global keyboard shortcuts, PWA/offline support —
installable, an update-available toast, and read-only offline via a service worker with per-route
runtime caching — a forms/feedback/accessibility hardening pass: a shared `422`-to-field error
mapper, toast variants with correct durations/`aria-live` politeness/stacking limits, three-tier
error boundaries (root/route/tile), a route-transition progress bar, width-stable button spinners,
and a WCAG 2.2 AA pass (44px touch targets, reduced-motion support, focus-ring/empty-state/copy
audits) — `SchemaForm` was pulled forward a milestone early in M05 since tile action dialogs need
it too — the full test suite: enforced coverage gates (≥80% overall, ≥95% on `src/auth/` and
`src/components/schema-form/`), an MSW mock layer generated against the same OpenAPI types the SDK
uses, and a Playwright e2e suite (`clients/web/tests/e2e/`) covering auth, dashboard, notes,
settings, admin, and PWA/offline flows — including axe scans of five key screens in both themes and
keyboard-traversal/focus-trap checks — against a real backend brought up by
`docker-compose.e2e.yml`; and `M12`'s deploy/performance/acceptance sweep: `clients/web/Dockerfile`
+ `nginx.conf`, a `web` Docker Compose service routed by Traefik, §22's bundle-size budgets enforced
in a `check:budget` script against the real build manifest, and route-level lazy-loading for the
tile action dialog. `milestones/client/M12-pwa-deploy-acceptance.md`'s own `**Status:**` line has
the exact split between what's automated/verified and what still needs a human with real
infrastructure (a live TLS deploy, iOS/Android home-screen install) — not everything in §25's
acceptance list is independently confirmable without both.

UI work follows [`docs/design-system/`](docs/design-system/), a components/tokens/guidelines
reference pulled from the "DISP Design System" Claude Design project — read its own `readme.md`
(especially the "Caveats" section) before using it: it's a starting point authored from a written
brief, not a source of truth to copy verbatim, and its inline-styled `.jsx` components need
translating into this repo's actual Tailwind/Radix conventions.

### Local development

Requires Node.js `>=22.11 <23` and `pnpm >=9.12`.

```sh
cd clients/web
pnpm install
pnpm dev            # Vite dev server on http://localhost:5173
```

§2.1 of the web spec requires the client and API to be same-origin in production (Traefik
path-routes `/api` to the backend container, §24.4, shipped in `M12`). `pnpm dev` doesn't run
through that Traefik routing at all, though, on purpose — `vite.config.ts`'s `server.proxy`
forwards `/api`, `/health`, and `/openapi.json` to `http://localhost:8000` instead, a permanent
fast-local-loop convenience, not a stand-in `M12` replaces. Run the real backend alongside `pnpm dev`
(`uv run uvicorn disp.main:app --reload` per the quickstart above) so those requests have
somewhere to land.

Regenerate the typed API client after any backend route change:

```sh
./dev openapi                 # from the repo root: writes openapi.json
cd clients/web && pnpm api:generate   # regenerates src/api/generated/, commit the result
```

Other useful commands, run from `clients/web/`:

```sh
pnpm typecheck   # tsc -b
pnpm lint        # eslint + prettier --check
pnpm fmt         # eslint --fix + prettier --write
pnpm test        # vitest run --coverage
pnpm test:watch  # vitest, interactive
pnpm build       # tsc -b && vite build -> dist/
pnpm preview     # serve the production build locally
pnpm test:e2e    # playwright, against docker-compose.e2e.yml — see below
```

`pnpm test:e2e` needs a real backend and a built `dist/`, not the dev server — from the repo root:

```sh
POSTGRES_PASSWORD=<anything> docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
  up -d --build
cd clients/web && pnpm build && pnpm test:e2e
```

`docker-compose.e2e.yml` (its own header comment has the full explanation) migrates and seeds one
deterministic admin user and exposes the API on `localhost:8000` — no Traefik in this loop, same
reasoning as `pnpm dev` above: `pnpm preview`'s own `preview.proxy` (`vite.config.ts`) makes
`/api`/`/health`/`/openapi.json` reach it same-origin without needing a full Traefik+`web`-container
stack for what wants to be a fast test loop. Run `docker compose -f docker-compose.yml -f
docker-compose.e2e.yml down -v` between runs for a clean database — the seeded admin can only be
created once.

### Production

`clients/web/Dockerfile` builds a two-stage image (`pnpm build` → static `dist/`, served by
`nginx:1.27-alpine`, non-root) and `docker-compose.yml` has a `web` service for it, routed by
Traefik exactly as `milestones/client/M12-pwa-deploy-acceptance.md` specifies: path-priority split
with `api` so `/api`, `/health`, and `/openapi.json` reach the backend container and everything else
reaches `web`. Traefik itself lives outside this repo now (see "Deployment" below) — `web` joins its
shared `edge` network and carries the routing labels, the same pattern `api` already uses. `web` is
also wired into the same GHCR + webhook auto-deploy pipeline the backend uses (`docs/operations.md`'s
"Webhook deploy" section). See that milestone doc's `**Status:**` line for exactly what has and
hasn't been independently verified yet (a live TLS deploy and mobile home-screen installs need real
infrastructure a CI/local check can't provide).

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  disp CLI  ──HTTP (PAT)──►  FastAPI app                          │
│                             ├─ /health, /api/auth, /api/dashboard│
│                             │  /api/settings  (core routers)     │
│                             ├─ /api/<domain>  (per-module router)│
│                             │                                    │
│                             ▼                                    │
│                          Registry ──discovers/wires──► modules   │
│                             │            (notes, ...)            │
│                             ▼                                    │
│                          Platform (settings, events, scheduler,  │
│                                    notifier, settings store,     │
│                                    read-only registry access)    │
└──────────────┬───────────────────────────────┬───────────────────┘
               │                               │
        Postgres 16                     Procrastinate (worker process)
   (schema per module + core)           background tasks, no Redis
```

- **Core** (`src/disp/core/`) is the backbone: auth, ACL, events, settings storage, the module
  registry, the dashboard/settings HTTP surface. It never imports anything from `disp/modules/`.
- **Modules** (`src/disp/modules/`) are self-contained plug-ins, each with its own Postgres schema
  and Alembic migration branch. Adding one requires zero edits to `core/` — see
  [`docs/adding-a-module.md`](docs/adding-a-module.md). Each module has its own README covering
  what it does and how to develop it — see
  [`src/disp/modules/notes/README.md`](src/disp/modules/notes/README.md) and
  [`src/disp/modules/plants/README.md`](src/disp/modules/plants/README.md).
- **The worker** (`src/disp/worker.py`) is a separate process running the same module wiring
  (event subscriptions, scheduled tasks) without an HTTP server, via Procrastinate.
- **The CLI** (`src/disp/cli/`) talks to the HTTP API exactly like any other client — it holds no
  special access.

## Where to read more

| Doc | Covers |
|---|---|
| [`TECHNICAL-SPEC.md`](TECHNICAL-SPEC.md) | The full normative specification this platform was built against. |
| [`TECHNICAL-SPEC-WEB.md`](TECHNICAL-SPEC-WEB.md) | Normative spec for the React PWA web client that consumes this API. |
| [`docs/auth.md`](docs/auth.md) | Credential types and lifetimes, refresh rotation and reuse detection, adopting an external OIDC provider later. |
| [`docs/adding-a-module.md`](docs/adding-a-module.md) | Four-step recipe for a new module, with a complete minimal example. |
| [`docs/operations.md`](docs/operations.md) | Backups, a verified restore drill, key rotation, log locations, health endpoints. |
| `./dev` (run with no args) | Every local dev command: `up`, `migrate`, `test`, `lint`, `seed`, `openapi`, … |

See "Web client" above for how to run what exists of `clients/web/` today, and
[`milestones/client/`](milestones/client/) for its build sequence.

`GET /api/dashboard/manifest` serializes each settings panel's schema as JSON Schema (with a secret
field marked `"x-secret": true`), including panels registered directly on the core platform (e.g.
`core.notifier`) under a synthetic `"core"` module entry — see `milestones/client/M00-backbone-amendments.md`.

## Deployment

`Dockerfile` builds a non-root, multi-stage production image. `docker-compose.yml` is the
reference production stack (Postgres, the API, the worker) — see `docs/operations.md` for running
it. TLS termination and routing are handled by Traefik, which lives outside this repo in a
separate `infra` project shared across every app on the host (not disp-specific) — this repo's
`docker-compose.yml` only joins its `edge` network and carries the routing labels.
`docker-compose.test.yml` is unrelated: a Postgres-only override `./dev up`/`./dev down` use for
local development (the automated test suite uses its own ephemeral testcontainers Postgres
instead, per `TECHNICAL-SPEC.md` §22.1). Every push to `prod` builds and pushes an image via
GitHub Actions, then triggers a pull-and-redeploy on the production host through a signed webhook
call — see `docs/operations.md`'s "Webhook deploy" section.
