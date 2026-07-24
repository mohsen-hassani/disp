# DISP

A self-hosted personal platform: a FastAPI backbone with a plug-in module contract, built-in auth
(JWT access tokens + refresh-token rotation with reuse detection + personal access tokens), and a
Typer CLI (`disp`). Ships with one demo module, `notes`, that exercises the full plug-in surface
(HTTP CRUD, a dashboard tile, a scheduled cleanup task, an event subscription) so you can see what
a real module looks like before writing your own.

## Quickstart

Requires [`uv`](https://docs.astral.sh/uv/) and Docker (for local Postgres).

```sh
git clone <this repo> disp && cd disp
uv sync

cp .env.example .env
# Edit .env: generate real secrets —
#   python -c "import secrets; print(secrets.token_urlsafe(48))"          # MYSTUFF_JWT_SECRET
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # MYSTUFF_SETTINGS_KEY
# For local dev, MYSTUFF_COOKIE_SECURE=false and MYSTUFF_ENV=development are fine as shipped.

./dev up          # starts a local Postgres 16 container
./dev migrate     # applies all Alembic branches + the Procrastinate schema
./dev seed        # creates a dev admin user and three sample notes

uv run uvicorn disp.main:app --reload   # API on http://localhost:8000
uv run python -m disp.worker            # in a second terminal: background task worker

uv run disp login --server http://localhost:8000   # prompts for the admin credentials ./dev seed printed
uv run disp notes list
```

Run `./dev test` (full suite, needs Docker for testcontainers) and `./dev lint` before committing.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  disp CLI  ──HTTP (PAT)──►  FastAPI app                         │
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
               │                                │
        Postgres 16                     Procrastinate (worker process)
   (schema per module + core)           background tasks, no Redis
```

- **Core** (`src/disp/core/`) is the backbone: auth, ACL, events, settings storage, the module
  registry, the dashboard/settings HTTP surface. It never imports anything from `disp/modules/`.
- **Modules** (`src/disp/modules/`) are self-contained plug-ins, each with its own Postgres schema
  and Alembic migration branch. Adding one requires zero edits to `core/` — see
  [`docs/adding-a-module.md`](docs/adding-a-module.md).
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

The web client's implementation is sequenced at [`milestones/client/M00-M12`](milestones/client/) —
`M00` (backend amendments enabling the client's generic settings UI) is complete; `M01` onward build
the client itself and haven't started yet.

`GET /api/dashboard/manifest` serializes each settings panel's schema as JSON Schema (with a secret
field marked `"x-secret": true`), including panels registered directly on the core platform (e.g.
`core.notifier`) under a synthetic `"core"` module entry — see `milestones/client/M00-backbone-amendments.md`.

## Deployment

`Dockerfile` builds a non-root, multi-stage production image. `docker-compose.yml` is the
reference production stack (Postgres, the API, the worker, Traefik for TLS via Let's Encrypt) —
see `docs/operations.md` for running it. `docker-compose.test.yml` is unrelated: a Postgres-only
override `./dev up`/`./dev down` use for local development (the automated test suite uses its own
ephemeral testcontainers Postgres instead, per `TECHNICAL-SPEC.md` §22.1).
