# M0 — Bootstrap project scaffold

**Status:** Complete

**Scope:** `pyproject.toml`, `.gitignore`, `.dockerignore`, `.env.example`, `src/disp/__init__.py`, `core/__init__.py`, `modules/__init__.py`, `dev` script stub, `git init`, `uv sync`.

Covers TECHNICAL-SPEC.md §3 (Technology stack), §4 (Repository layout), §4.1 (Package naming).

---

## §3. Technology stack

All versions are **minimum** versions. The implementer MUST pin exact versions in `pyproject.toml` using `>=` constraints as shown and MUST commit a lock file (`uv.lock`).

| Concern | Package | Constraint |
|---|---|---|
| Runtime | Python | `>=3.12,<3.14` |
| Package manager | `uv` | latest |
| Web framework | `fastapi` | `>=0.115` |
| ASGI server | `uvicorn[standard]` | `>=0.32` |
| ORM | `sqlalchemy[asyncio]` | `>=2.0.36` |
| DB driver (app) | `asyncpg` | `>=0.30` |
| DB driver (queue) | `psycopg[binary,pool]` | `>=3.2` |
| Migrations | `alembic` | `>=1.14` |
| Validation | `pydantic` | `>=2.9` |
| Config | `pydantic-settings` | `>=2.6` |
| Task queue | `procrastinate` | `>=2.9` |
| Notifications | `apprise` | `>=1.9` |
| Password hashing | `pwdlib[argon2]` | `>=0.2.1` |
| JWT | `pyjwt` | `>=2.9` |
| Symmetric encryption | `cryptography` | `>=43` |
| Recurrence rules | `python-dateutil` | `>=2.9` |
| Structured logging | `structlog` | `>=24.4` |
| CLI framework | `typer` | `>=0.15` |
| CLI rendering | `rich` | `>=13.9` |
| HTTP client | `httpx` | `>=0.28` |
| CLI config paths | `platformdirs` | `>=4.3` |
| TOML writing | `tomli-w` | `>=1.1` |
| Rate limiting | `slowapi` | `>=0.1.9` |

**Dev dependencies:** `pytest>=8.3`, `pytest-asyncio>=0.24`, `pytest-cov>=6.0`, `testcontainers[postgres]>=4.8`, `ruff>=0.8`, `mypy>=1.13`, `types-python-dateutil`.

**Explicitly forbidden:** Redis, Celery, RabbitMQ, `passlib`, `python-jose`, any external identity provider, any ORM other than SQLAlchemy.

## §4. Repository layout

The implementer MUST create exactly this tree. Files marked *(generated)* are produced by tooling, not hand-written.

```
disp/
├── pyproject.toml
├── uv.lock                                (generated)
├── alembic.ini
├── docker-compose.yml
├── docker-compose.test.yml
├── Dockerfile
├── .env.example
├── .dockerignore
├── .gitignore
├── dev                                     (executable bash script)
├── README.md
├── docs/
│   ├── auth.md
│   ├── adding-a-module.md
│   └── operations.md
├── src/
│   └── disp/
│       ├── __init__.py                     (exports __version__)
│       ├── main.py                         (uvicorn entrypoint: app = create_app())
│       ├── worker.py                       (procrastinate worker entrypoint)
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py                   (Settings, get_settings)
│       │   ├── contract.py                 (ModuleManifest, PlatformModule, *Spec, TileData)
│       │   ├── registry.py                 (discovery, validation, topo-sort, wiring)
│       │   ├── platform.py                 (Platform facade object)
│       │   ├── app.py                      (create_app factory, lifespan, middleware)
│       │   ├── db.py                       (engine, session factory, Base, naming convention)
│       │   ├── events.py                   (EventBus, publish_after_commit)
│       │   ├── scheduler.py                (Procrastinate app, @task, daily planner)
│       │   ├── notifier.py                 (Apprise dispatch, routing, notify task)
│       │   ├── settings_store.py           (SettingsStore, Fernet encryption)
│       │   ├── dashboard.py                (dashboard router: manifest, tiles)
│       │   ├── errors.py                   (ProblemDetail, AppError hierarchy, handlers)
│       │   ├── logging.py                  (structlog config, RequestIdMiddleware)
│       │   ├── pagination.py               (cursor encode/decode, Page model)
│       │   ├── health.py                   (health router)
│       │   ├── models.py                   (SQLAlchemy models for schema `core`)
│       │   ├── cli_admin.py                (server-side admin CLI: seed-admin, etc.)
│       │   ├── auth/
│       │   │   ├── __init__.py             (PUBLIC SURFACE — see §10.1)
│       │   │   ├── dependencies.py         (current_user, require_admin, optional_user)
│       │   │   ├── passwords.py            (hash_password, verify_password, policy)
│       │   │   ├── tokens.py               (access JWT, refresh, PAT)
│       │   │   ├── sessions.py             (rotation, family revocation)
│       │   │   ├── invites.py              (create, accept)
│       │   │   ├── acl.py                  (can, grant, revoke, list_grants)
│       │   │   ├── schemas.py              (Pydantic request/response models)
│       │   │   ├── routes.py               (/api/auth/*)
│       │   │   └── oidc.py                 (documented stub — see §10.10)
│       │   └── migrations/
│       │       ├── env.py
│       │       ├── script.py.mako
│       │       └── versions/               (branch label: "core")
│       ├── modules/
│       │   ├── __init__.py                 (namespace only; MUST stay empty)
│       │   └── notes/
│       │       ├── __init__.py             (get_module())
│       │       ├── manifest.py
│       │       ├── models.py
│       │       ├── schemas.py
│       │       ├── service.py
│       │       ├── router.py
│       │       ├── tiles.py
│       │       ├── events.py
│       │       └── migrations/
│       │           └── versions/           (branch label: "notes")
│       └── cli/
│           ├── __init__.py
│           ├── main.py                     (typer app, global flags)
│           ├── config.py                   (profile file read/write)
│           ├── client.py                   (httpx wrapper, error mapping)
│           ├── render.py                   (Rich table/JSON output helpers)
│           └── commands/
│               ├── __init__.py
│               ├── auth.py                 (login, logout, whoami, tokens)
│               ├── dashboard.py
│               ├── notes.py
│               ├── modules.py
│               └── health.py
└── tests/
    ├── conftest.py
    ├── factories.py
    ├── core/
    │   ├── test_registry.py
    │   ├── test_events.py
    │   ├── test_settings_store.py
    │   ├── test_notifier.py
    │   ├── test_scheduler.py
    │   ├── test_pagination.py
    │   ├── test_errors.py
    │   └── test_boundaries.py
    ├── auth/
    │   ├── test_passwords.py
    │   ├── test_login.py
    │   ├── test_refresh_rotation.py
    │   ├── test_pat.py
    │   ├── test_invites.py
    │   ├── test_acl.py
    │   └── test_dependencies.py
    ├── modules/
    │   └── test_notes.py
    ├── fixtures_modules/
    │   ├── hello/                          (plug-in proof module — see §22.4)
    │   ├── broken_manifest/
    │   └── cyclic_a/ , cyclic_b/
    └── cli/
        └── test_cli.py
```

### 4.1 Package naming (mandatory)

The backbone package is named **`core`**, not `platform`. A top-level package named `platform` shadows the Python standard-library `platform` module and breaks third-party imports. The implementer MUST NOT rename it.

The distribution is `disp`; the CLI console script is `disp`.

`pyproject.toml` MUST declare:

```toml
[project.scripts]
disp = "disp.cli.main:app"
disp-admin = "disp.core.cli_admin:app"
```

> **Resolved naming decision:** the spec's own snippet here originally read `stuff = "disp.cli.main:app"`, contradicting §10.7's explicit `disp_pat_` PAT prefix and every `disp login`/`disp notes ...` example elsewhere. Resolved with the user: **everything user-facing is `disp`** (console script, PAT prefix, User-Agent). `MYSTUFF_` env-var prefix and FastAPI `title="MyStuff"` are left as-is (self-consistent legacy branding).

## Notes from implementation

- `scripts/backup.sh` and `docker-compose.test.yml` are required by other sections (§23.3, and the tree above) but are added even though not itemized everywhere; see M16.
- Bootstrap also ran `uv python pin 3.12` and `uv sync`, and created a placeholder `README.md` (required by `pyproject.toml`'s `readme` field) filled in properly at M16.
