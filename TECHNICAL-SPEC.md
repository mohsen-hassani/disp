# DISP Platform — Technical Specification

**Document type:** Implementation specification
**Version:** 1.0
**Status:** Approved for implementation
**Scope:** Platform backbone + auth subsystem + `notes` demo module + `disp` Typer CLI

---

## How to read this document

This specification is **normative and complete**. An implementing agent must not invent behaviour that is not described here. Where a decision could reasonably go two ways, this document picks one and states it.

Keywords follow RFC 2119: **MUST**, **MUST NOT**, **SHOULD**, **MAY**.

If the implementer believes a requirement is impossible, contradictory, or unsafe, it **MUST** stop and report the conflict rather than substituting its own design.

---

## Table of Contents

1. [Goals and non-goals](#1-goals-and-non-goals)
2. [System overview](#2-system-overview)
3. [Technology stack](#3-technology-stack)
4. [Repository layout](#4-repository-layout)
5. [Configuration](#5-configuration)
6. [Database conventions and DDL](#6-database-conventions-and-ddl)
7. [Migrations](#7-migrations)
8. [The module contract](#8-the-module-contract)
9. [Module registry and startup](#9-module-registry-and-startup)
10. [Auth subsystem](#10-auth-subsystem)
11. [Authorization (ACL)](#11-authorization-acl)
12. [Event bus](#12-event-bus)
13. [Scheduler and task queue](#13-scheduler-and-task-queue)
14. [Notifier](#14-notifier)
15. [Settings store](#15-settings-store)
16. [Dashboard API](#16-dashboard-api)
17. [HTTP API conventions](#17-http-api-conventions)
18. [Notes module](#18-notes-module)
19. [Typer CLI (`disp`)](#19-typer-cli-disp)
20. [Logging and observability](#20-logging-and-observability)
21. [Security requirements](#21-security-requirements)
22. [Testing requirements](#22-testing-requirements)
23. [Deployment](#23-deployment)
24. [Developer tooling](#24-developer-tooling)
25. [Acceptance criteria](#25-acceptance-criteria)
26. [Out of scope](#26-out-of-scope)
27. [Appendix A — Error code registry](#appendix-a--error-code-registry)
28. [Appendix B — Worked examples](#appendix-b--worked-examples)

---

## 1. Goals and non-goals

### 1.1 Goals

| # | Goal |
|---|---|
| G1 | A single deployable FastAPI application into which self-contained feature modules plug with **zero edits to platform code**. |
| G2 | A declarative module contract covering API routes, dashboard tiles, settings panels, scheduled jobs, and notification types. |
| G3 | Self-hosted authentication supporting a browser client (cookie + JWT) and a terminal client (personal access tokens), behind one dependency. |
| G4 | Per-resource sharing authorization (read / write / owner) usable by any module. |
| G5 | Postgres-only infrastructure: no Redis, no RabbitMQ, no external identity provider. |
| G6 | A working demo module (`notes`) and a working terminal client (`disp`) proving the contract end to end. |
| G7 | A documented, non-breaking upgrade path to an external OIDC provider. |

### 1.2 Non-goals

Do **not** implement: the plants, habits, or shopping-list modules; a web UI; native mobile apps; multi-tenancy beyond per-user data; OIDC/SAML; SCIM; email sending for password reset; TOTP/MFA; horizontal scaling of the API beyond a single container.

### 1.3 Operating assumptions

- Expected user count: 1–20. Invite-only. All users are trusted individuals.
- Expected request volume: < 10 req/s sustained.
- Expected background job volume: < 10 000 jobs/day.
- Single Postgres instance, single API container, single worker container.

---

## 2. System overview

```
                          ┌───────────────────────────┐
   Browser / PWA ────────▶│                           │
   disp CLI (PAT) ──────▶│   api  (FastAPI/uvicorn)  │
                          │                           │
                          │  ┌─────────────────────┐  │
                          │  │ core (backbone)     │  │
                          │  │  registry           │  │
                          │  │  auth               │  │
                          │  │  events             │  │
                          │  │  scheduler          │  │
                          │  │  notifier           │  │
                          │  │  settings           │  │
                          │  └─────────┬───────────┘  │
                          │            │ discovers    │
                          │  ┌─────────▼───────────┐  │
                          │  │ modules/notes       │  │
                          │  └─────────────────────┘  │
                          └────────────┬──────────────┘
                                       │
                          ┌────────────▼──────────────┐
                          │   PostgreSQL 16           │
                          │   schemas: core, notes,   │
                          │            public (queue) │
                          └────────────▲──────────────┘
                                       │
                          ┌────────────┴──────────────┐
                          │  worker (procrastinate)   │──▶ Apprise ──▶ ntfy / email / …
                          └───────────────────────────┘
```

Two processes share one codebase and one database. The `api` process serves HTTP; the `worker` process executes deferred and periodic tasks. Both perform module discovery at startup so that modules' tasks and event handlers exist in both.

---

## 3. Technology stack

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

---

## 4. Repository layout

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

---

## 5. Configuration

All configuration is read from environment variables via `pydantic-settings`. Prefix: `DISP`. `.env` is loaded in development only.

### 5.1 Settings model

`src/disp/core/config.py` MUST define:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DISP", env_file=".env", extra="forbid")
```

### 5.2 Variable registry

| Variable | Type | Required | Default | Validation |
|---|---|---|---|---|
| `DISP_DATABASE_URL` | str | yes | — | MUST start with `postgresql+asyncpg://` |
| `DISP_DATABASE_URL_SYNC` | str | no | derived | Derived from above by replacing `+asyncpg` with `+psycopg`; used by Alembic and Procrastinate |
| `DISP_JWT_SECRET` | SecretStr | yes | — | MUST be ≥ 32 characters; startup fails otherwise |
| `DISP_SETTINGS_KEY` | SecretStr | yes | — | MUST be a valid urlsafe-base64 32-byte Fernet key |
| `DISP_ACCESS_TOKEN_TTL_SECONDS` | int | no | `900` | 60–3600 |
| `DISP_REFRESH_TOKEN_TTL_SECONDS` | int | no | `2592000` (30 d) | 3600–7776000 |
| `DISP_INVITE_TTL_SECONDS` | int | no | `604800` (7 d) | 3600–2592000 |
| `DISP_PAT_DEFAULT_TTL_DAYS` | int \| None | no | `None` (no expiry) | ≥ 1 if set |
| `DISP_MODULES` | str | no | `""` | Comma-separated allow-list of module domains. Empty = load all discovered. |
| `DISP_BASE_URL` | str | yes | — | Public URL, e.g. `https://disp.example.com`. Used to build invite links. No trailing slash. |
| `DISP_CORS_ORIGINS` | str | no | `""` | Comma-separated origins |
| `DISP_COOKIE_SECURE` | bool | no | `true` | MUST be `true` in production |
| `DISP_COOKIE_DOMAIN` | str \| None | no | `None` | |
| `DISP_LOG_LEVEL` | str | no | `INFO` | One of DEBUG/INFO/WARNING/ERROR |
| `DISP_LOG_FORMAT` | str | no | `json` | `json` or `console` |
| `DISP_DAILY_PLANNER_CRON` | str | no | `0 6 * * *` | 5-field cron |
| `DISP_TIMEZONE` | str | no | `Europe/Amsterdam` | IANA name; used for "today" boundaries |
| `DISP_RATE_LIMIT_ENABLED` | bool | no | `true` | |
| `DISP_ENV` | str | no | `production` | `production` \| `development` \| `test` |

`get_settings()` MUST be `@lru_cache`-decorated and MUST be the only way settings are obtained.

### 5.3 Startup validation

On boot the application MUST fail fast (log a fatal error, exit code 1) if:
- any required variable is missing;
- `JWT_SECRET` is shorter than 32 characters;
- `SETTINGS_KEY` is not a valid Fernet key;
- `DISP_ENV == "production"` and `COOKIE_SECURE` is false;
- the database is unreachable after 5 retries with 2-second backoff.

### 5.4 `.env.example`

MUST be committed, MUST list every variable in §5.2 with placeholder values, and MUST include a comment showing how to generate secrets:

```
# python -c "import secrets; print(secrets.token_urlsafe(48))"
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 6. Database conventions and DDL

### 6.1 Conventions

- One PostgreSQL 16 database.
- **One schema per module.** The backbone owns `core`. The notes module owns `notes`. Procrastinate owns `public`.
- Modules MUST NOT create foreign keys across schemas. A module referencing a user stores `user_id UUID` with **no** FK to `core.users`. Rationale: preserves the extraction seam and prevents accidental joins. Referential integrity for users is enforced in application code.
- Modules MUST NOT read or write another schema's tables. Cross-module data flows through service functions or events.
- All primary keys are `UUID`, generated with `gen_random_uuid()` (extension `pgcrypto`, enabled by the first core migration).
- All timestamps are `TIMESTAMPTZ`, stored in UTC.
- Every table has `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`. Tables that are mutated also have `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`, maintained by application code (not a trigger).
- Soft delete only where §18 specifies it.

SQLAlchemy `Base` MUST configure this naming convention so Alembic autogenerate produces stable names:

```python
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
```

### 6.2 Schema `core` — DDL

The following is the authoritative target state. Alembic migrations MUST produce exactly this.

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS core;

-- ─────────────────────────────────────────────────────────────
CREATE TABLE core.users (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email             TEXT        NOT NULL,
    display_name      TEXT        NOT NULL,
    password_hash     TEXT        NULL,
    is_active         BOOLEAN     NOT NULL DEFAULT TRUE,
    is_admin          BOOLEAN     NOT NULL DEFAULT FALSE,
    external_issuer   TEXT        NULL,
    external_subject  TEXT        NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_users_display_name_len CHECK (char_length(display_name) BETWEEN 1 AND 100),
    CONSTRAINT ck_users_external_pair CHECK (
        (external_issuer IS NULL) = (external_subject IS NULL)
    ),
    CONSTRAINT ck_users_has_credential CHECK (
        password_hash IS NOT NULL OR external_subject IS NOT NULL
    )
);
CREATE UNIQUE INDEX uq_users_email_lower ON core.users (lower(email));
CREATE UNIQUE INDEX uq_users_external
    ON core.users (external_issuer, external_subject)
    WHERE external_subject IS NOT NULL;

-- ─────────────────────────────────────────────────────────────
CREATE TABLE core.invites (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email            TEXT        NOT NULL,
    token_hash       TEXT        NOT NULL UNIQUE,
    is_admin         BOOLEAN     NOT NULL DEFAULT FALSE,
    created_by       UUID        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
    expires_at       TIMESTAMPTZ NOT NULL,
    accepted_at      TIMESTAMPTZ NULL,
    accepted_user_id UUID        NULL REFERENCES core.users(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_invites_email_lower ON core.invites (lower(email));
CREATE UNIQUE INDEX uq_invites_pending_email
    ON core.invites (lower(email))
    WHERE accepted_at IS NULL;

-- ─────────────────────────────────────────────────────────────
CREATE TABLE core.sessions (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
    family_id           UUID        NOT NULL,
    refresh_token_hash  TEXT        NOT NULL UNIQUE,
    previous_session_id UUID        NULL REFERENCES core.sessions(id) ON DELETE SET NULL,
    device_label        TEXT        NULL,
    user_agent          TEXT        NULL,
    ip_address          TEXT        NULL,
    issued_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at          TIMESTAMPTZ NOT NULL,
    rotated_at          TIMESTAMPTZ NULL,
    revoked_at          TIMESTAMPTZ NULL,
    revoked_reason      TEXT        NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_sessions_revoked_reason CHECK (
        revoked_reason IS NULL OR revoked_reason IN
        ('logout','rotation','reuse_detected','password_change','admin','expired')
    )
);
CREATE INDEX ix_sessions_user_id  ON core.sessions (user_id);
CREATE INDEX ix_sessions_family_id ON core.sessions (family_id);

-- ─────────────────────────────────────────────────────────────
CREATE TABLE core.api_tokens (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
    name         TEXT        NOT NULL,
    token_hash   TEXT        NOT NULL UNIQUE,
    token_prefix TEXT        NOT NULL,
    last_used_at TIMESTAMPTZ NULL,
    expires_at   TIMESTAMPTZ NULL,
    revoked_at   TIMESTAMPTZ NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_api_tokens_name_len CHECK (char_length(name) BETWEEN 1 AND 64)
);
CREATE UNIQUE INDEX uq_api_tokens_user_name
    ON core.api_tokens (user_id, name) WHERE revoked_at IS NULL;
CREATE INDEX ix_api_tokens_user_id ON core.api_tokens (user_id);

-- ─────────────────────────────────────────────────────────────
CREATE TABLE core.acl (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_type TEXT        NOT NULL,
    resource_id   TEXT        NOT NULL,
    user_id       UUID        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
    permission    TEXT        NOT NULL,
    granted_by    UUID        NULL REFERENCES core.users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_acl_permission CHECK (permission IN ('read','write','owner'))
);
CREATE UNIQUE INDEX uq_acl_resource_user
    ON core.acl (resource_type, resource_id, user_id);
CREATE INDEX ix_acl_user_lookup ON core.acl (user_id, resource_type);

-- ─────────────────────────────────────────────────────────────
CREATE TABLE core.settings (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NULL REFERENCES core.users(id) ON DELETE CASCADE,
    module_domain   TEXT        NOT NULL,
    key             TEXT        NOT NULL,
    value_json      JSONB       NULL,
    value_encrypted BYTEA       NULL,
    is_secret       BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_settings_one_value CHECK (
        (value_json IS NULL) <> (value_encrypted IS NULL)
    ),
    CONSTRAINT ck_settings_secret_storage CHECK (
        (is_secret = TRUE  AND value_encrypted IS NOT NULL) OR
        (is_secret = FALSE AND value_json      IS NOT NULL)
    )
);
CREATE UNIQUE INDEX uq_settings_scope
    ON core.settings (user_id, module_domain, key) NULLS NOT DISTINCT;

-- ─────────────────────────────────────────────────────────────
CREATE TABLE core.notification_log (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID        NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
    notification_type TEXT        NOT NULL,
    title             TEXT        NOT NULL,
    body              TEXT        NOT NULL,
    channel_ids       TEXT[]      NOT NULL DEFAULT '{}',
    status            TEXT        NOT NULL,
    error             TEXT        NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_notification_log_status CHECK (
        status IN ('sent','partial','failed','no_channels')
    )
);
CREATE INDEX ix_notification_log_user_created
    ON core.notification_log (user_id, created_at DESC);
```

`uq_settings_scope` relies on `NULLS NOT DISTINCT`, available in PostgreSQL 15+. PostgreSQL 16 is the pinned version, so this is valid.

### 6.3 Session management

- The async engine MUST be created with `pool_size=10`, `max_overflow=5`, `pool_pre_ping=True`.
- `async_session_maker` MUST use `expire_on_commit=False`.
- A FastAPI dependency `get_session()` MUST yield one session per request, commit on success, roll back on exception, and always close.
- Background tasks MUST create their own session via an async context manager; they MUST NOT reuse a request session.

---

## 7. Migrations

### 7.1 Structure

Alembic runs in **multi-branch** mode. Each module owns an independent version history with its own branch label and its own version table.

`alembic.ini` MUST define one section per module:

```ini
[alembic]
script_location = src/disp/core/migrations

[core]
script_location = src/disp/core/migrations
version_locations = src/disp/core/migrations/versions
version_table = alembic_version_core
version_table_schema = core

[notes]
script_location = src/disp/modules/notes/migrations
version_locations = src/disp/modules/notes/migrations/versions
version_table = alembic_version_notes
version_table_schema = notes
```

### 7.2 `env.py` requirements

A single shared `env.py` (referenced by every module's `script_location` through a symlink or a thin re-export module) MUST:

1. Read `DISP_DATABASE_URL_SYNC` from the environment; never hard-code a URL.
2. Determine the active branch from the Alembic config section name.
3. Set `version_table`, `version_table_schema`, and `include_schemas=True`.
4. Install an `include_object` hook that **excludes any table whose schema is not the branch's own schema**, so `alembic revision --autogenerate` for `notes` never emits DDL for `core`.
5. Create the target schema (`CREATE SCHEMA IF NOT EXISTS <schema>`) before running migrations.
6. Import the branch's models module so metadata is populated.

### 7.3 Commands

| Command | Effect |
|---|---|
| `./dev migrate` | Upgrade every branch to head, in order: `core`, then modules alphabetically |
| `./dev migrate core` | Upgrade only `core` |
| `./dev makemigration <branch> "<message>"` | `alembic --name=<branch> revision --autogenerate -m "<message>"` |
| `./dev downgrade <branch> <rev>` | Downgrade one branch |

The `api` container MUST NOT run migrations automatically. Migrations run as an explicit step (`./dev migrate` or a one-shot compose command).

### 7.4 Required initial migrations

- `core` branch, revision 1: `pgcrypto` extension, `core` schema, all tables in §6.2.
- `notes` branch, revision 1: `notes` schema and the table in §18.2.

---

## 8. The module contract

`src/disp/core/contract.py` MUST define exactly the following. Field names, types, and defaults are normative.

### 8.1 Specification models

```python
DOMAIN_RE = r"^[a-z][a-z0-9_]{1,31}$"
KEY_RE = r"^[a-z][a-z0-9_]{1,31}\.[a-z][a-z0-9_]{1,63}$"  # "<domain>.<name>"

# A client route relative to the module's own /<domain> namespace: "", "new",
# "{plant_id}", "{plant_id}/edit". Leading slashes are rejected on purpose.
SUBPATH_RE = r"^$|^[a-z0-9_{}-]+(?:/[a-z0-9_{}-]+)*$"
ICON_RE = r"^[a-z][a-z0-9-]{0,31}$"  # kebab-case lucide icon name


class TileSize(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class TileNavSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(min_length=1, max_length=32)   # "Manage plants"
    path: str = Field(default="", pattern=SUBPATH_RE)  # sub-path under /<domain>


class TileSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(pattern=KEY_RE)
    title: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    size: TileSize = TileSize.MEDIUM
    refresh_seconds: int = Field(default=300, ge=10, le=86400)
    order: int = Field(default=100, ge=0, le=1000)
    nav: TileNavSpec | None = None  # requires the manifest to declare client_nav


class SettingsPanelSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(pattern=KEY_RE)
    title: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    schema_model: type[BaseModel]  # the Pydantic model describing the form
    scope: Literal["user", "global"] = "user"


class ScheduledJobSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=KEY_RE)  # unique task name, e.g. "notes.cleanup"
    cron: str  # 5-field cron, validated at registration
    description: str | None = None


class NotificationTypeSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(pattern=KEY_RE)
    title: str = Field(min_length=1, max_length=80)
    description: str | None = None
    default_enabled: bool = True


class ClientNavSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(min_length=1, max_length=32)
    icon: str = Field(default="box", pattern=ICON_RE)  # lucide icon name
    order: int = Field(default=100, ge=0, le=1000)
    routes: tuple[str, ...] = ()  # advisory: sub-paths under /<domain>


class ModuleManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    domain: str = Field(pattern=DOMAIN_RE)
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str | None = Field(default=None, max_length=300)
    dependencies: tuple[str, ...] = ()
    tiles: tuple[TileSpec, ...] = ()
    settings_panels: tuple[SettingsPanelSpec, ...] = ()
    scheduled_jobs: tuple[ScheduledJobSpec, ...] = ()
    notification_types: tuple[NotificationTypeSpec, ...] = ()
    client_nav: ClientNavSpec | None = None
```

**Cross-field validation** — `ModuleManifest` MUST enforce, via a model validator, that every `key` in `tiles`, `settings_panels`, `scheduled_jobs`, and `notification_types` begins with `f"{domain}."`. Violations raise `ValueError` at import time.

**Client surface (amendment A3).** `client_nav` declares that a module ships client screens and how they present (label, icon, order). Its **route namespace is always `/<domain>/…`, derived from the domain and never declarable** — the client translates tile deep links by stripping the `/api` prefix (`/api/plants/x` → `/plants/x`), so a declarable base path would silently break every one of them. `routes` is advisory documentation of the intended URL surface; the server cannot ship the screens.

Declaring `client_nav` does not create screens. A client renders the nav entry only if it also has screens for that domain, so a module ahead of its client degrades to dashboard-only rather than linking somewhere that 404s (WEB-SPEC §12.2).

`ModuleManifest` MUST additionally enforce that a `TileSpec.nav` is only present when `client_nav` is set — a tile nav button links into a namespace the module must have claimed — and that no `client_nav.routes` entry is an absolute path.

### 8.2 Tile data models

```python
class TileAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str  # "quick_add"
    label: str
    method: Literal["POST", "PATCH", "DELETE"]
    path: str  # "/api/notes"
    body_schema: dict[str, Any] | None = None  # JSON Schema, or None


class TileItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    primary: str  # main line of text
    secondary: str | None = None
    timestamp: datetime | None = None
    done: bool | None = None  # renders a checkbox when not None
    href: str | None = None  # deep link into the module's API


class TileData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    count: int | None = None  # headline number, if meaningful
    items: list[TileItem] = []
    actions: list[TileAction] = []
    empty_text: str = "Nothing here"
    generated_at: datetime
```

### 8.3 The module interface

```python
class PlatformModule(Protocol):
    manifest: ModuleManifest

    def register(self, platform: "Platform") -> None: ...
    def api_router(self) -> APIRouter | None: ...
    def tile_provider(self, key: str) -> TileProvider | None: ...
```

`TileProvider` is `Callable[[TileContext], Awaitable[TileData]]`, where:

```python
@dataclass(frozen=True)
class TileContext:
    user: CurrentUser
    session: AsyncSession
    platform: "Platform"
    now: datetime  # timezone-aware, in DISP_TIMEZONE
```

Every module package MUST expose a module-level function:

```python
def get_module() -> PlatformModule: ...
```

It MUST be idempotent and side-effect free apart from constructing the object.

### 8.4 The `Platform` facade

`src/disp/core/platform.py` MUST define a `Platform` dataclass that is the **only** object passed to `register()`:

```python
@dataclass
class Platform:
    settings: Settings
    events: EventBus
    scheduler: SchedulerFacade  # .task(name), .defer(name, **kwargs)
    notifier: NotifierFacade  # .send(...)
    store: SettingsStore
    registry: "Registry"  # read-only accessors only
```

Modules MUST NOT import `create_app`, the SQLAlchemy engine, or anything from `disp.core.auth` other than the three public names in §10.1.

---

## 9. Module registry and startup

### 9.1 Discovery algorithm

`Registry.discover()` MUST execute exactly these steps:

1. Enumerate candidate packages with `pkgutil.iter_modules(disp.modules.__path__)`. Order is not guaranteed; sort names alphabetically for determinism.
2. If `DISP_MODULES` is non-empty, filter to that allow-list. A named module that does not exist is a **fatal** error.
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

### 9.2 Wiring

For each module, in dependency order, `Registry.wire(app, platform)` MUST:

1. Call `module.register(platform)`.
2. If `module.api_router()` returns a router, include it with `prefix=f"/api/{domain}"` and `tags=[domain]`.
3. For each `ScheduledJobSpec`, look up the task registered under that name in the scheduler; a missing task is **fatal**. Register it as periodic with the spec's cron.
4. Index tiles, settings panels, and notification types into read-only dictionaries keyed by their `key`.

`register()` MUST NOT perform I/O. Database work belongs in request handlers or tasks.

### 9.3 Application factory

`create_app()` MUST, in order:

1. Load settings; configure logging (§20).
2. Create the async engine and session maker.
3. Construct `EventBus`, `SettingsStore`, `SchedulerFacade`, `NotifierFacade`, then the `Platform`.
4. Build the `FastAPI` instance with `title="DISP"`, `version=__version__`, `openapi_url="/openapi.json"`, `docs_url="/docs"` (only when `DISP_ENV != "production"`; otherwise `None`).
5. Install middleware in this order (outermost first): `RequestIdMiddleware`, `CORSMiddleware`, `SlowAPIMiddleware`.
6. Register exception handlers (§17.4).
7. Mount core routers: `/health`, `/api/auth`, `/api/dashboard`, `/api/settings`.
8. Run `Registry.discover()` and `Registry.wire()`.
9. Register a lifespan handler that opens the Procrastinate connector on startup and closes it, plus the DB engine, on shutdown.

The registry MUST be attached as `app.state.registry` and the platform as `app.state.platform`.

### 9.4 Worker entrypoint

`src/disp/worker.py` MUST perform steps 1–3 and 8 of §9.3 (settings, logging, engine, platform, discovery, wiring of tasks and event handlers) **without** constructing a FastAPI app, then hand control to Procrastinate's worker. This guarantees module tasks and event subscriptions exist in the worker process.

---

## 10. Auth subsystem

### 10.1 Public surface (architectural constraint)

`src/disp/core/auth/__init__.py` MUST contain exactly:

```python
from disp.core.auth.acl import Permission, can
from disp.core.auth.dependencies import CurrentUser, current_user, require_admin

__all__ = ["CurrentUser", "Permission", "can", "current_user", "require_admin"]
```

**No module under `disp/modules/` may import any other name from `disp.core.auth` or from any of its submodules.** This is enforced by an automated test (§22.5). Violating it is a build failure, not a style issue. This constraint is what makes replacing in-app auth with an external OIDC provider a change confined to `disp/core/auth/`.

### 10.2 `CurrentUser`

```python
@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: UUID
    email: str
    display_name: str
    is_admin: bool
    auth_method: Literal["access_token", "api_token"]
    token_id: UUID | None  # api_tokens.id when auth_method == "api_token"
```

### 10.3 Passwords

`passwords.py` MUST expose:

```python
def hash_password(plain: str) -> str
def verify_password(plain: str, hashed: str) -> bool
def validate_password_policy(plain: str, *, email: str) -> None   # raises PasswordPolicyError
```

Requirements:

- Hashing uses `pwdlib.PasswordHash.recommended()` (Argon2id).
- Policy: length ≥ 12 and ≤ 128; MUST NOT equal the email address case-insensitively; MUST NOT be one of the 100 most common passwords, supplied as a committed constant list in `passwords.py`. No composition rules (no forced symbols/digits).
- `verify_password` MUST return `False` rather than raise on a malformed hash.
- A module-level constant `DUMMY_HASH` MUST hold a pre-computed Argon2id hash of a random string, used for timing equalisation (§10.4).

### 10.4 Login

**`POST /api/auth/login`**

Request (`application/json`):
```json
{"email": "a@b.com", "password": "correct horse battery staple", "device_label": "firefox-laptop"}
```
`device_label` is optional, max 64 chars.

Algorithm (order is normative):

1. Look up the user by `lower(email)`.
2. If not found: call `verify_password(password, DUMMY_HASH)` and discard the result, then return `401 core.auth.invalid_credentials`.
3. If found but `is_active` is false: still perform the verify, then return `403 core.auth.account_disabled`.
4. If `password_hash` is NULL: return `401 core.auth.invalid_credentials`.
5. Verify. On failure return `401 core.auth.invalid_credentials`.
6. Create a session: new `family_id = uuid4()`, refresh token per §10.5, `expires_at = now + REFRESH_TOKEN_TTL`, record `user_agent` (truncated to 256 chars) and `ip_address` from `X-Forwarded-For` (first hop) or the peer address.
7. Issue an access JWT per §10.6.

Responses:

| Status | Body |
|---|---|
| `200` | `{"access_token": "...", "token_type": "bearer", "expires_in": 900, "user": {UserOut}}` |
| `401` | problem, `code=core.auth.invalid_credentials` |
| `403` | problem, `code=core.auth.account_disabled` |
| `422` | validation problem |
| `429` | problem, `code=core.platform.rate_limited` |

`200` MUST also set:

```
Set-Cookie: disp_refresh=<token>; Path=/api/auth; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000
```

`Secure` is omitted only when `DISP_COOKIE_SECURE` is false. `Domain` is set only when configured.

The error message text for `core.auth.invalid_credentials` MUST be identical for unknown-email and wrong-password cases.

### 10.5 Refresh tokens and rotation

- Format: `secrets.token_urlsafe(32)` (43 characters). Opaque; no structure.
- Stored as `sha256(token).hexdigest()` in `sessions.refresh_token_hash`. The plaintext is never persisted or logged.
- A `family_id` groups every token descended from one login.

**`POST /api/auth/refresh`**

- Reads the token from the `disp_refresh` cookie. It MUST NOT accept the token from a request body or header.
- MUST require the header `X-Requested-With: disp`; absence returns `403 core.auth.csrf_required`. This is the CSRF defence, since the endpoint is cookie-authenticated.

Algorithm:

1. Hash the presented token; look up the session.
2. Not found → `401 core.auth.invalid_refresh_token`.
3. `revoked_at IS NOT NULL` **or** `rotated_at IS NOT NULL` → **reuse detected**: revoke every session in the same `family_id` (set `revoked_at = now()`, `revoked_reason = 'reuse_detected'`), log at `WARNING` with `user_id` and `family_id`, clear the cookie, return `401 core.auth.refresh_token_reused`.
4. `expires_at < now()` → mark `revoked_reason='expired'`, return `401 core.auth.refresh_token_expired`.
5. User inactive → `403 core.auth.account_disabled`.
6. Otherwise rotate: create a new session row with the same `family_id`, `previous_session_id` set to the current row; set the current row's `rotated_at = now()`, `revoked_at = now()`, `revoked_reason='rotation'`. Issue a new access token and set a new cookie.

Steps 1–6 MUST run inside a single transaction with `SELECT … FOR UPDATE` on the session row.

Response `200`: same shape as login. Errors clear the cookie with `Max-Age=0`.

**`POST /api/auth/logout`** — requires the cookie and `X-Requested-With`. Revokes the whole `family_id` with reason `logout`, clears the cookie, returns `204`. Returns `204` even when the cookie is absent or unknown (no information leak).

### 10.6 Access tokens

- Algorithm `HS256`, secret `DISP_JWT_SECRET`.
- Claims: `sub` (user id, string UUID), `iat`, `exp`, `jti` (uuid4), `typ` = `"access"`, `email`, `adm` (bool).
- TTL from `DISP_ACCESS_TOKEN_TTL_SECONDS`.
- Verification MUST enforce `typ == "access"`, signature, and expiry with `leeway=0`.
- Access tokens are **not** revocable before expiry. This is accepted: revocation acts on the refresh family, and 15 minutes is the maximum exposure. This MUST be stated in `docs/auth.md`.

### 10.7 Personal access tokens

- Format: `disp_pat_` + `secrets.token_urlsafe(32)`. Total length 53.
- `token_hash` = `sha256(full_token).hexdigest()`.
- `token_prefix` = the first 18 characters (`disp_pat_` + 8), stored for display.
- The plaintext is returned **once**, in the creation response only. It is never retrievable again and never logged.

Endpoints:

| Method | Path | Auth | Behaviour |
|---|---|---|---|
| `GET` | `/api/auth/tokens` | any | Lists the caller's non-revoked tokens: `id`, `name`, `token_prefix`, `created_at`, `last_used_at`, `expires_at` |
| `POST` | `/api/auth/tokens` | **access_token only** | Creates a token. Body: `{"name": str, "expires_in_days": int \| null}`. Returns `201` with the plaintext in field `token`. |
| `DELETE` | `/api/auth/tokens/{id}` | any | Sets `revoked_at`. `204`. `404` if not the caller's. |

**A PAT MUST NOT be usable to create another PAT.** `POST /api/auth/tokens` MUST reject `auth_method == "api_token"` with `403 core.auth.pat_cannot_mint`. This prevents a leaked token from minting persistence.

`last_used_at` MUST be updated on successful authentication, but at most once per 60 seconds per token (compare before writing) to avoid a write on every request.

### 10.8 The `current_user` dependency

Signature:

```python
async def current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser
```

Resolution:

1. No `Authorization` header → `401 core.auth.missing_credentials`, response includes `WWW-Authenticate: Bearer`.
2. Header not matching `^Bearer (.+)$` → `401 core.auth.malformed_credentials`.
3. Credential starts with `disp_pat_` → PAT path: hash, look up, reject if `revoked_at` set (`401 core.auth.token_revoked`) or `expires_at` past (`401 core.auth.token_expired`); load user; reject inactive (`403 core.auth.account_disabled`); update `last_used_at` subject to the 60-second rule; return `CurrentUser(auth_method="api_token", token_id=...)`.
4. Otherwise JWT path: decode and validate; on any `PyJWTError` → `401 core.auth.invalid_token`; expired → `401 core.auth.token_expired`; load user by `sub`; missing → `401 core.auth.invalid_token`; inactive → `403 core.auth.account_disabled`; return `CurrentUser(auth_method="access_token", token_id=None)`.

The refresh cookie MUST NOT authenticate any endpoint other than `/api/auth/refresh` and `/api/auth/logout`.

`require_admin` wraps `current_user` and raises `403 core.auth.admin_required` when `is_admin` is false.

### 10.9 Invites

**`POST /api/auth/invites`** — admin only. Body `{"email": str, "is_admin": bool = false}`.

- Rejects an email that already belongs to a user (`409 core.auth.user_exists`).
- Rejects a second pending invite for the same email (`409 core.auth.invite_pending`) — enforced by `uq_invites_pending_email`.
- Token: `secrets.token_urlsafe(32)`, stored hashed.
- Returns `201` with `{"id", "email", "token", "accept_url", "expires_at"}` where `accept_url = f"{DISP_BASE_URL}/accept-invite?token={token}"`. The plaintext token appears only here. Delivery to the invitee is the admin's problem; the system sends no email.

**`GET /api/auth/invites`** — admin only. Lists pending invites without tokens.

**`DELETE /api/auth/invites/{id}`** — admin only. Hard-deletes a pending invite. `204`.

**`POST /api/auth/accept-invite`** — unauthenticated. Body `{"token", "display_name", "password"}`.

1. Hash and look up. Not found → `404 core.auth.invite_not_found`.
2. `accepted_at` set → `409 core.auth.invite_used`.
3. `expires_at` past → `410 core.auth.invite_expired`.
4. Validate the password policy → `422 core.auth.password_policy` with the specific reason in `detail`.
5. If a user with that email now exists → `409 core.auth.user_exists`.
6. Create the user with `is_admin` from the invite; mark the invite accepted; create a session and issue tokens exactly as login does.
7. Return `201` with the login response body and the refresh cookie.

Steps 1–6 run in one transaction.

### 10.10 Password change and the OIDC stub

**`POST /api/auth/password`** — authenticated, **access_token only** (`403 core.auth.pat_insufficient` for PATs). Body `{"current_password", "new_password"}`. Verifies the current password, validates the new one, rehashes, then revokes **all** sessions for the user except the caller's current family, with reason `password_change`. Returns `204`.

**`GET /api/auth/me`** — returns `UserOut` plus `auth_method`.

`src/disp/core/auth/oidc.py` MUST exist and MUST contain a documented stub:

```python
async def resolve_external_token(token: str, session: AsyncSession) -> CurrentUser:
    """Reserved for a future external OIDC provider.

    Planned implementation:
      1. Fetch and cache the issuer's JWKS from OIDC discovery.
      2. Validate signature, `iss`, `aud`, and `exp`.
      3. Look up core.users by (external_issuer, external_subject).
      4. If absent, link by verified email on first login; otherwise 403.

    Wiring point: a fourth branch in `dependencies.current_user`, taken when
    the JWT's `iss` claim is not this application. No other file changes.
    """
    raise NotImplementedError("External OIDC is not enabled in this deployment.")
```

It MUST NOT be called from anywhere. A test asserts it raises `NotImplementedError`.

### 10.11 Admin bootstrap

`disp-admin seed-admin --email <e> --display-name <n>` MUST create the first admin. The password is read from the `DISP_SEED_PASSWORD` environment variable, or generated with `secrets.token_urlsafe(16)` and printed once. The command MUST refuse to run if any user already exists, exiting `1` with a clear message. There is no HTTP route that creates the first user.

---

## 11. Authorization (ACL)

### 11.1 Model

```python
class Permission(StrEnum):
    READ = "read"
    WRITE = "write"
    OWNER = "owner"


_RANK = {Permission.READ: 1, Permission.WRITE: 2, Permission.OWNER: 3}

ACTION_REQUIRES: dict[str, Permission] = {
    "read": Permission.READ,
    "list": Permission.READ,
    "create": Permission.WRITE,
    "update": Permission.WRITE,
    "delete": Permission.WRITE,
    "share": Permission.OWNER,
    "unshare": Permission.OWNER,
    "transfer": Permission.OWNER,
}
```

### 11.2 API

```python
async def can(session, user: CurrentUser, action: str,
              resource_type: str, resource_id: str | UUID) -> bool
async def require(session, user, action, resource_type, resource_id) -> None   # raises 403
async def grant(session, *, resource_type, resource_id, user_id,
                permission: Permission, granted_by: UUID) -> None
async def revoke(session, *, resource_type, resource_id, user_id) -> None
async def list_grants(session, *, resource_type, resource_id) -> list[Grant]
async def readable_ids(session, *, user_id, resource_type) -> list[str]
```

Semantics:

- `can` returns `True` when a row exists for `(resource_type, resource_id, user_id)` whose permission rank ≥ the rank required by `action`.
- An unknown `action` raises `ValueError` — it is a programming error, not a denial.
- `can` performs **no implicit ownership inference**. A module that creates a resource MUST call `grant(..., permission=OWNER)` in the same transaction. Failing to do so leaves the resource inaccessible; this is intentional and MUST be covered by a test.
- Admin users are **not** implicitly granted access to other users' resources. `is_admin` governs invite management only.
- `readable_ids` exists so modules can filter list queries without N+1 permission checks.

---

## 12. Event bus

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

---

## 13. Scheduler and task queue

### 13.1 Procrastinate setup

- One `procrastinate.App` in `disp/core/scheduler.py`, using `PsycopgConnector` with `DISP_DATABASE_URL_SYNC`.
- Procrastinate's own tables live in the `public` schema (its default). No customisation.
- `procrastinate schema --apply` runs as part of `./dev migrate` and as a one-shot compose command, before the worker starts.

### 13.2 Task registration

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

### 13.3 The daily planner

A periodic task named `core.daily_planner`, cron from `DISP_DAILY_PLANNER_CRON`, MUST:

1. Receive Procrastinate's single `timestamp: int` argument.
2. Log start with the resolved local date in `DISP_TIMEZONE`.
3. Iterate `registry.scheduled_jobs`, and for each, log its name. (Actual per-module fan-out is each module's responsibility via its own periodic jobs; the planner exists to prove the mechanism and to provide a single hook for future cross-module planning.)
4. Log completion with a count.

It MUST be idempotent: running it twice for the same day produces no duplicate side effects.

### 13.4 Worker configuration

The worker container runs `python -m disp.worker`, which MUST call `app.run_worker_async(concurrency=4, install_signal_handlers=True, listen_notify=True)` after discovery. Graceful shutdown on `SIGTERM` within 30 seconds.

---

## 14. Notifier

### 14.1 Channel configuration

Stored in the settings store under domain `core`, per user:

- Key `notifier.channels`, non-secret, JSON array of:
  ```json
  {"id": "phone", "label": "Phone push", "enabled": true}
  ```
  `id` matches `^[a-z][a-z0-9_-]{0,31}$`.
- Key `notifier.url.<channel_id>`, **secret**, a single Apprise URL string. Stored encrypted; never returned by any API.
- Key `notifier.routing`, non-secret, an object mapping notification-type key → array of channel ids.

### 14.2 Resolution

`NotifierFacade.send(user_id, notification_type, title, body, url=None)` MUST:

1. Validate that `notification_type` is a registered `NotificationTypeSpec` key; unknown → `ValueError`.
2. Defer the Procrastinate task `core.deliver_notification` with the arguments. `send` returns immediately; it never performs network I/O inline.

The task `core.deliver_notification` MUST:

1. Load `notifier.routing`; take the channel list for the type.
2. If absent, fall back to every channel with `enabled: true`.
3. If still empty, write `core.notification_log` with `status='no_channels'` and return without error.
4. Decrypt each channel's Apprise URL, build one `apprise.Apprise()` instance, add all URLs, and call `notify(title=..., body=...)`.
5. Write `core.notification_log` with `status` = `sent` (all succeeded), `partial`, or `failed`, and `error` holding a truncated (1000 char) diagnostic.
6. Raise on total failure so Procrastinate retries; do **not** raise on partial success.

Apprise URLs MUST NOT appear in logs, tracebacks, or error responses. The log line records channel ids only.

### 14.3 Settings panel

The core notifier registers a settings panel `core.notifier` with scope `user`, whose schema model exposes `channels`, `routing`, and a write-only `urls` mapping. `GET /api/settings/core` MUST return secret values as the literal string `"***"` when set and `null` when unset. `PUT` MUST treat `"***"` as "leave unchanged".

---

## 15. Settings store

```python
class SettingsStore:
    async def get(self, session, *, user_id: UUID | None, domain: str,
                  key: str, default: Any = None) -> Any
    async def set(self, session, *, user_id: UUID | None, domain: str,
                  key: str, value: Any, is_secret: bool = False) -> None
    async def get_all(self, session, *, user_id: UUID | None,
                      domain: str, reveal_secrets: bool = False) -> dict[str, Any]
    async def delete(self, session, *, user_id: UUID | None,
                     domain: str, key: str) -> None
```

- Non-secret values are stored in `value_json`; secrets are `json.dumps`-ed, encoded UTF-8, encrypted with Fernet using `DISP_SETTINGS_KEY`, and stored in `value_encrypted`.
- `get_all` with `reveal_secrets=False` returns `"***"` for secrets. Only the notifier task uses `reveal_secrets=True`.
- Changing a key from non-secret to secret (or back) is allowed; `set` rewrites both columns consistently to satisfy `ck_settings_one_value`.
- Decryption failure (wrong key) MUST raise `SettingsDecryptionError`, be logged at `ERROR`, and surface as `500 core.settings.decryption_failed` — never as a silent `None`.
- `user_id=None` denotes a global setting; only admins may write global settings through the HTTP API.

**HTTP:**

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/api/settings/{domain}` | Caller's values for that domain, secrets masked. `404` if the domain has no registered settings panel. |
| `PUT` | `/api/settings/{domain}` | Body validated against the panel's `schema_model`. Partial update: only supplied keys change. Returns the masked result. |

---

## 16. Dashboard API

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

Renders one tile. `404 core.dashboard.tile_not_found` for an unknown key. Errors here **do** propagate as `500`, since the caller asked for that specific tile.

---

## 17. HTTP API conventions

### 17.1 Paths and versioning

- All application routes live under `/api/`. Module routes are `/api/{domain}/...`.
- No URL version segment. The OpenAPI document version tracks `__version__`.
- Resource collections are plural nouns. Sub-resources nest at most one level.
- Trailing slashes are not used; FastAPI's `redirect_slashes` MUST be disabled.

### 17.2 Status codes

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
| `413` | Request payload exceeds a size limit |
| `415` | Payload media type not accepted |
| `422` | Schema validation failure |
| `429` | Rate limited; `Retry-After` header set |
| `500` | Unhandled server error |

A resource that exists but that the caller may not read MUST return `404`, not `403`, to avoid existence disclosure. `403` is reserved for cases where the caller can already see the resource but lacks the specific permission (e.g. write on a shared item).

### 17.3 Error envelope

All errors use RFC 9457 `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Invalid credentials",
  "status": 401,
  "detail": "The email or password is incorrect.",
  "instance": "/api/auth/login",
  "code": "core.auth.invalid_credentials",
  "request_id": "01JF3K…"
}
```

`code` is machine-readable and drawn from Appendix A. `detail` is human-readable and MUST NOT contain secrets, hashes, SQL, or stack traces.

`422` responses add `errors`: a list of `{"loc": [...], "msg": "...", "type": "..."}`.

### 17.4 Exception handlers

`create_app` MUST register handlers for: `AppError` (the project's base class carrying `status`, `code`, `title`, `detail`), `RequestValidationError`, `HTTPException`, and `Exception`. The catch-all handler logs the full traceback at `ERROR` with the request id and returns a generic `500 core.platform.internal_error` whose `detail` is `"An unexpected error occurred."` — never the exception text.

Codes raised by these handlers rather than by a domain use the `core.platform.*` subsystem (Appendix A).

### 17.5 Pagination

Cursor-based. Query parameters `limit` (default 20, min 1, max 100) and `cursor` (opaque).

The cursor is `base64url(json.dumps({"ts": <iso8601>, "id": "<uuid>"}))`, encoding the sort key of the last returned item. Decoding failure → `400 core.pagination.invalid_cursor`.

Response envelope for every list endpoint:

```json
{"items": [...], "next_cursor": "eyJ0cyI6…", "has_more": true}
```

`next_cursor` is `null` when `has_more` is false. Total counts are not provided.

### 17.6 CORS, headers, rate limiting

- CORS is enabled only when `DISP_CORS_ORIGINS` is non-empty; `allow_credentials=True`, methods `GET, POST, PATCH, DELETE, OPTIONS`, headers `Authorization, Content-Type, X-Requested-With`.
- Every response carries `X-Request-ID`.
- Rate limits (`slowapi`, keyed by client IP unless noted), applied when `DISP_RATE_LIMIT_ENABLED`:

| Endpoint | Limit |
|---|---|
| `POST /api/auth/login` | 10/minute per IP **and** 5/minute per submitted email |
| `POST /api/auth/refresh` | 60/minute per IP |
| `POST /api/auth/accept-invite` | 10/hour per IP |
| `POST /api/auth/tokens` | 20/hour per user |
| `POST /api/auth/password` | 5/hour per user |
| all other routes | 300/minute per IP |

Exceeding a limit returns `429` with `Retry-After`.

### 17.7 OpenAPI

- Every route MUST declare `response_model`, `status_code`, `summary`, and a `responses` dict documenting each non-2xx status it can return.
- Every route MUST carry exactly one tag: its domain, or `auth`, `dashboard`, `settings`, `health`.
- `operation_id` MUST be set explicitly as `{tag}_{action}` (e.g. `notes_list`, `auth_login`) so generated clients have stable method names.

---

## 18. Notes module

The demo module. It exists to prove the contract, and its implementation quality is held to the same standard as the backbone.

### 18.1 Manifest

```python
MANIFEST = ModuleManifest(
    domain="notes",
    name="Notes",
    version="1.0.0",
    description="Quick personal notes with pinning and full-text search.",
    dependencies=(),
    tiles=(
        TileSpec(
            key="notes.latest",
            title="Latest notes",
            description="Your most recent notes",
            size=TileSize.MEDIUM,
            refresh_seconds=120,
            order=10,
        ),
    ),
    settings_panels=(),
    scheduled_jobs=(
        ScheduledJobSpec(
            name="notes.purge_deleted",
            cron="30 3 * * *",
            description="Hard-delete notes soft-deleted over 30 days ago",
        ),
    ),
    notification_types=(
        NotificationTypeSpec(
            key="notes.reminder",
            title="Note reminder",
            description="Sent when a pinned note is stale",
        ),
    ),
)
```

The `notification_types` entry exists to exercise the manifest; nothing sends it in this release. This MUST be noted in a code comment.

### 18.2 Schema `notes` — DDL

```sql
CREATE SCHEMA IF NOT EXISTS notes;

CREATE TABLE notes.notes (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL,          -- no FK: see §6.1
    title      TEXT        NULL,
    body       TEXT        NOT NULL,
    pinned     BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL,
    CONSTRAINT ck_notes_body_len  CHECK (char_length(body)  BETWEEN 1 AND 20000),
    CONSTRAINT ck_notes_title_len CHECK (title IS NULL OR char_length(title) BETWEEN 1 AND 200)
);

CREATE INDEX ix_notes_user_created
    ON notes.notes (user_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX ix_notes_user_pinned
    ON notes.notes (user_id, pinned, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX ix_notes_search
    ON notes.notes USING GIN (to_tsvector('simple', coalesce(title,'') || ' ' || body));
```

### 18.3 Endpoints

Base prefix `/api/notes`, tag `notes`. Every route depends on `current_user`.

| Method | Path | Operation id | Description |
|---|---|---|---|
| `GET` | `` | `notes_list` | Paginated list |
| `POST` | `` | `notes_create` | Create |
| `GET` | `/{note_id}` | `notes_get` | Read one |
| `PATCH` | `/{note_id}` | `notes_update` | Partial update |
| `DELETE` | `/{note_id}` | `notes_delete` | Soft delete |
| `POST` | `/{note_id}/share` | `notes_share` | Grant another user access |

**`GET /api/notes`** query parameters:

| Name | Type | Default | Notes |
|---|---|---|---|
| `limit` | int | 20 | 1–100 |
| `cursor` | str | null | §17.5 |
| `q` | str | null | Full-text search over title+body, ≤ 200 chars |
| `pinned` | bool | null | Filter |

Ordering: `pinned DESC, created_at DESC, id DESC`. Excludes `deleted_at IS NOT NULL`. Returns notes the caller owns **or** has an ACL grant on — implemented with a single query using `readable_ids`, not a per-row check.

**`POST /api/notes`** body:

```json
{"title": "Optional", "body": "Required, 1–20000 chars", "pinned": false}
```

MUST, in one transaction: insert the note, call `grant(resource_type="notes.note", resource_id=str(id), user_id=caller, permission=OWNER, granted_by=caller)`, and `publish_after_commit(NoteCreated(...))`. Returns `201` with `Location: /api/notes/{id}`.

**`PATCH`** accepts any subset of `title`, `body`, `pinned`; requires `write`. Updates `updated_at`. Publishes `NoteUpdated`.

**`DELETE`** requires `write`. Sets `deleted_at`. Returns `204`. Publishes `NoteDeleted`. Repeating the call on an already-deleted note returns `404`.

**`POST /{note_id}/share`** requires `owner`. Body `{"email": str, "permission": "read"|"write"}`. Resolves the email to a user (`404 modules.notes.user_not_found` if absent), then `grant`s. Returns `204`. Sharing with oneself returns `400 modules.notes.cannot_share_with_self`.

All single-note routes: resolve the note, then `require(action)`. Absent or not readable → `404 modules.notes.not_found`.

### 18.4 Events

```python
@dataclass(frozen=True, slots=True)
class NoteCreated:
    note_id: UUID
    user_id: UUID
    title: str | None


@dataclass(frozen=True, slots=True)
class NoteUpdated:
    note_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True)
class NoteDeleted:
    note_id: UUID
    user_id: UUID
```

In `register()`, the module subscribes a handler to `NoteCreated` that logs at `INFO`: `event="note_created" note_id=… user_id=…`. This exists so the bus is provably exercised end to end.

### 18.5 Tile provider

`notes.latest` returns a `TileData` with:
- `count` = number of non-deleted notes readable by the user;
- `items` = the 5 most recent, `primary` = title or the first 60 characters of body with an ellipsis, `secondary` = `"pinned"` when pinned else `None`, `timestamp` = `created_at`, `href` = `/api/notes/{id}`;
- one action: `TileAction(id="quick_add", label="Add note", method="POST", path="/api/notes", body_schema={"type":"object","required":["body"],"properties":{"body":{"type":"string"}}})`;
- `empty_text` = `"No notes yet"`.

### 18.6 Scheduled job

`notes.purge_deleted`, registered via `platform.scheduler.task("notes.purge_deleted")`, hard-deletes rows where `deleted_at < now() - interval '30 days'` and logs the count.

---

## 19. Typer CLI (`disp`)

### 19.1 Configuration file

Path: `platformdirs.user_config_dir("disp")/config.toml`, created with mode `0600`. The CLI MUST refuse to read a config file whose mode is group- or world-readable, exiting `3` with instructions to `chmod 600`.

```toml
default_profile = "default"

[profiles.default]
server = "https://disp.example.com"
token = "disp_pat_…"
email = "me@example.com"
```

The token MUST NOT be written anywhere else, and MUST NOT appear in `--verbose` output (redact to the prefix).

### 19.2 Global options

| Option | Effect |
|---|---|
| `--profile, -p TEXT` | Select a profile (default: `default_profile`) |
| `--server TEXT` | Override the server URL for one invocation |
| `--json` | Emit raw JSON instead of Rich tables; disables all decoration |
| `--no-color` | Disable colour (also honours `NO_COLOR`) |
| `--verbose, -v` | Log requests (method, URL, status, duration) to stderr |
| `--version` | Print version and exit |

Human output goes to **stdout**; diagnostics and errors go to **stderr**. `--json` output MUST be a single valid JSON document on stdout with nothing else, so it is pipeable to `jq`.

### 19.3 Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Generic failure |
| `2` | Usage error (Typer default) |
| `3` | Authentication or configuration error (no token, 401, bad file mode) |
| `4` | Network error (DNS, connection refused, timeout) |
| `5` | Server error (5xx) |
| `6` | Not found (404) |

### 19.4 Commands

**`disp login [--server URL] [--profile NAME]`**

1. Prompt for the server URL if not supplied and not in config.
2. Prompt for email; prompt for password with `hide_input=True`.
3. `POST /api/auth/login`.
4. With the returned access token, `POST /api/auth/tokens` with `name = f"cli@{socket.gethostname()}"[:64]`. If that name exists (`409`), append `-2`, `-3`, … up to `-9`.
5. Persist `server`, `email`, and the PAT to the profile. Discard the password and the access token immediately; never write them.
6. Print `Logged in as <display_name> <email>` and the token prefix.

The refresh cookie is discarded. The CLI authenticates only with the PAT.

**`disp logout [--profile NAME]`** — `DELETE /api/auth/tokens/{id}` for the stored token (resolved by matching `token_prefix` from `GET /api/auth/tokens`), then removes the profile. Succeeds even if the server is unreachable, warning that the token was not revoked remotely.

**`disp whoami`** — `GET /api/auth/me`; prints display name, email, admin flag, auth method.

**`disp tokens list`** / **`disp tokens revoke <id>`** / **`disp tokens create <name> [--expires-days N]`** — the last prints the plaintext once with a warning that it will not be shown again.

**`disp health`** — `GET /health`; prints status, version, database, worker last-seen. Exit `1` if status is not `ok`.

**`disp modules`** — `GET /api/dashboard/manifest`; Rich table with columns Domain, Name, Version, Tiles, Jobs.

**`disp dashboard`** — `GET /api/dashboard/tiles`; renders each tile as a Rich panel showing title, count, up to 5 items, and available actions. Empty tiles render their `empty_text` dimmed.

**`disp notes list [--limit N] [--pinned/--no-pinned] [-q TEXT] [--all]`** — Rich table: Id (first 8 chars), Pinned marker, Title, Created (relative, e.g. "2h ago"), Preview (60 chars). `--all` pages through every cursor.

**`disp notes add [BODY] [--title TEXT] [--pin]`** — if `BODY` is omitted and stdin is not a TTY, read the body from stdin (enabling `echo "x" | disp notes add`). If omitted and stdin is a TTY, open `$EDITOR`. Prints the new note id.

**`disp notes show <ID>`** — accepts a full UUID or an unambiguous prefix of ≥ 4 characters; an ambiguous prefix lists the candidates and exits `1`.

**`disp notes edit <ID> [--title TEXT] [--body TEXT] [--pin/--unpin]`** — with no flags, opens `$EDITOR` pre-filled with the current body.

**`disp notes rm <ID> [--yes]`** — confirms unless `--yes`.

**`disp notes share <ID> --email E --permission read|write`**

### 19.5 Client behaviour

`cli/client.py` MUST:

- Use one `httpx.Client` with `timeout=httpx.Timeout(10.0, connect=5.0)` and `follow_redirects=False`.
- Send `Authorization: Bearer <pat>` and `User-Agent: disp-cli/<version>`.
- Map responses to exceptions: `401` → `AuthError` (exit 3, message "Not logged in or token revoked — run `disp login`"), `403` → `PermissionError` (exit 1), `404` → `NotFoundError` (exit 6), `429` → retry once after `Retry-After` then fail (exit 1), `5xx` → `ServerError` (exit 5), transport errors → `NetworkError` (exit 4).
- Surface the problem-detail `detail` field as the user-facing message when present; fall back to a generic message.
- Never print a traceback unless `--verbose`.

---

## 20. Logging and observability

- `structlog` with a JSON renderer when `DISP_LOG_FORMAT=json`, Rich console renderer otherwise.
- Standard-library logging is routed through structlog; uvicorn access logs are disabled in favour of the middleware below.
- Every log record carries: `timestamp` (ISO 8601 UTC), `level`, `event`, `logger`, and, when available, `request_id`, `user_id`, `module`.
- `RequestIdMiddleware` reads `X-Request-ID` or generates a UUID4, binds it to the structlog context, and echoes it in the response header.
- One `INFO` line per request: `event="http_request"`, `method`, `path`, `status`, `duration_ms`, `user_id`.
- One `INFO` line per task execution: `event="task_completed"`, `task`, `job_id`, `duration_ms`, `attempt`.
- **Never logged:** passwords, password hashes, refresh tokens, PAT plaintexts, Apprise URLs, `Authorization` header values, cookie values, `DISP_JWT_SECRET`, `DISP_SETTINGS_KEY`. A test asserts these strings do not appear in captured log output for the login and notifier paths.

**`GET /health`** (unauthenticated) returns:

```json
{"status":"ok","version":"1.0.0","database":"ok",
 "modules":["notes"],"worker_last_seen":"2026-07-24T09:00:00Z"}
```

`status` is `ok` only when the database responds to `SELECT 1` within 2 seconds. `worker_last_seen` is derived from the most recent successful Procrastinate job; `null` is not an error. Degraded → `503` with `status: "degraded"`.

`GET /health/live` returns `200 {"status":"ok"}` without touching the database.

---

## 21. Security requirements

| # | Requirement |
|---|---|
| S1 | Passwords hashed with Argon2id via `pwdlib`. Plaintext never persisted or logged. |
| S2 | Refresh tokens and PATs stored as SHA-256 hashes; plaintext returned exactly once. |
| S3 | Refresh-token reuse revokes the entire token family and logs a `WARNING`. |
| S4 | The refresh cookie is `HttpOnly`, `Secure` (production), `SameSite=Lax`, path-scoped to `/api/auth`. |
| S5 | Cookie-authenticated endpoints require `X-Requested-With: disp`. |
| S6 | Login is constant-time with respect to account existence (dummy verify on the miss path) and returns an identical error for both failure modes. |
| S7 | PATs cannot mint PATs or change passwords. |
| S8 | Authorization is deny-by-default: absence of an ACL row denies. No implicit ownership. |
| S9 | Unreadable resources return `404`, not `403`. |
| S10 | All SQL goes through SQLAlchemy constructs. Raw SQL, if used, is parameterised. String interpolation into SQL is forbidden. |
| S11 | Settings secrets are Fernet-encrypted at rest with a key held only in the environment. |
| S12 | The catch-all exception handler never leaks exception text, SQL, or stack traces to the client. |
| S13 | Rate limits per §17.6. |
| S14 | `docs_url` and `redoc_url` are disabled when `DISP_ENV=production`. |
| S15 | The container runs as a non-root user (`uid 10001`). |
| S16 | Dependencies are pinned via a committed lock file. |

---

## 22. Testing requirements

### 22.1 Infrastructure

- `pytest` with `asyncio_mode = "auto"`.
- A real PostgreSQL 16 via `testcontainers`, started once per session. SQLite is forbidden.
- Per-test isolation: each test runs in a transaction that is rolled back at teardown. Tests that need committed data use a dedicated fixture that truncates afterwards.
- `httpx.ASGITransport` against the real app; no mocking of FastAPI internals.
- Apprise is mocked at the `apprise.Apprise.notify` boundary. No test performs outbound network I/O.
- Time-dependent tests use `freezegun` or explicit injected `now` parameters — never `sleep`.

### 22.2 Coverage

Overall line coverage ≥ 85 %. `src/disp/core/auth/` ≥ 95 %. The build fails below either threshold.

The overall gate is `pytest --cov-fail-under=85`. The per-directory gate is a separate
`coverage report --include=… --fail-under=95` over the same `.coverage` file, because `coverage.py`
has no per-path threshold setting. Both live in `./dev test`; add a line there per gated directory.

### 22.3 Required test cases

**Auth**
1. Password hash/verify round-trip; `verify_password` returns `False` for a malformed hash.
2. Policy rejects: < 12 chars, > 128 chars, password equal to email, a common-list password.
3. Login succeeds and sets a cookie with the correct attributes.
4. Login with unknown email and login with wrong password return byte-identical bodies (modulo `request_id`) and both `401`.
5. Login on a disabled account returns `403`.
6. Refresh rotates: new access token issued, new cookie set, old refresh token now rejected.
7. Refresh replay of a rotated token returns `401 core.auth.refresh_token_reused` **and** every session in the family has `revoked_at` set.
8. Refresh without `X-Requested-With` returns `403`.
9. Expired refresh token returns `401 core.auth.refresh_token_expired`.
10. Logout revokes the family and clears the cookie; a second logout still returns `204`.
11. PAT creation returns plaintext once; the same value never appears in the list response.
12. A PAT authenticates a normal endpoint successfully.
13. A PAT is rejected by `POST /api/auth/tokens` with `403 core.auth.pat_cannot_mint`.
14. A PAT is rejected by `POST /api/auth/password`.
15. A revoked PAT returns `401`; an expired PAT returns `401`.
16. `last_used_at` updates on first use and does not update again within 60 seconds.
17. `current_user` returns an equivalent `CurrentUser` (excluding `auth_method`) for a JWT and a PAT belonging to the same user.
18. Missing, malformed, and garbage `Authorization` headers each return the documented `401` code.
19. Invite create → accept → login works; the token is single-use (second accept returns `409`).
20. An expired invite returns `410`.
21. A second pending invite for the same email returns `409`.
22. Non-admin invite creation returns `403`.
23. Password change revokes other sessions but not the caller's.

**ACL**
24. `can` honours the rank ladder (read < write < owner) for each action.
25. Absence of a grant denies.
26. `can` with an unknown action raises `ValueError`.
27. An admin has no implicit access to another user's resource.
28. `readable_ids` returns owned and shared ids and nothing else.

**Registry**
29. Discovery loads `notes` and exposes it in the manifest.
30. A fixture module with a domain/package-name mismatch is fatal.
31. Duplicate tile keys across two fixture modules are fatal.
32. A missing dependency is fatal.
33. A dependency cycle is fatal and the message names both modules.
34. `DISP_MODULES` restricts loading; naming a non-existent module is fatal.

**Events**
35. A subscribed handler receives a published event.
36. A raising handler is logged and does not prevent the next handler from running; `publish` returns one `HandlerFailure`.
37. `publish_after_commit` dispatches only after commit and not after rollback.

**Notifier**
38. `send` with an unknown notification type raises `ValueError`.
39. Delivery with no configured channels writes `status='no_channels'` and does not raise.
40. Delivery calls Apprise with the decrypted URLs and logs `status='sent'`.
41. Apprise URLs never appear in captured logs.

**Settings**
42. Secret round-trip encrypts at rest (`value_encrypted` non-null, `value_json` null) and decrypts correctly.
43. `get_all` masks secrets by default and reveals them only when asked.
44. A wrong key raises `SettingsDecryptionError`.

**Notes**
45. Create returns `201`, persists to `notes.notes`, creates an OWNER ACL row, and emits `NoteCreated` (assert the handler ran).
46. List excludes soft-deleted notes and another user's notes.
47. Reading another user's note returns `404`.
48. Share with `read` lets the grantee read but not update (update returns `403`).
49. Full-text search matches on title and body.
50. Pagination returns a stable, non-overlapping sequence across pages.
51. `purge_deleted` removes only rows deleted more than 30 days ago.

**Platform**
52. `GET /health` returns `ok` with a live database.
53. `GET /api/dashboard/tiles` renders the notes tile; a provider that raises yields the fallback tile rather than a `500`.
54. `GET /api/dashboard/tiles/{unknown}` returns `404`.
55. Every route in the OpenAPI document has a unique `operation_id`.
56. `oidc.resolve_external_token` raises `NotImplementedError`.

**CLI** (against the ASGI app via a transport-injected client)
57. `disp login` writes a `0600` config containing a PAT and no password.
58. A config file with mode `0644` is refused with exit `3`.
59. `disp notes add` from piped stdin creates a note.
60. `--json` output parses as JSON and contains no ANSI escapes.
61. A `401` from the server exits `3` with a "run `disp login`" message.

### 22.4 The plug-in proof

`tests/fixtures_modules/hello/` MUST contain a minimal module (manifest, one tile returning a static `TileData`, no router, no DB). A test MUST:

1. Copy or path-inject it so discovery finds it.
2. Restart the app factory.
3. Assert it appears in `GET /api/dashboard/manifest` and its tile renders in `GET /api/dashboard/tiles`.
4. Assert via `git diff --name-only` (or an equivalent recorded file list) that **no file under `src/disp/core/` was modified** to make this work.

### 22.5 The boundary test

`tests/core/test_boundaries.py` MUST parse every `.py` file under `src/disp/modules/` with `ast`, collect all `ImportFrom` and `Import` nodes referencing `disp.core.auth`, and assert that the only imported names are `CurrentUser`, `Permission`, `can`, `current_user`, `require_admin`, and that no submodule (`disp.core.auth.tokens`, etc.) is imported at all. The failure message MUST name the offending file, line, and symbol.

A second assertion in the same file: no file under `src/disp/modules/` imports `disp.core.app`, `disp.core.db.engine`, or another module's package (`disp.modules.<other>`).

---

## 23. Deployment

### 23.1 Dockerfile

Multi-stage. Stage 1 installs dependencies with `uv` into a virtualenv. Stage 2 is `python:3.12-slim`, copies the venv and `src/`, creates user `app` (uid 10001), sets `PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1`, and drops privileges. No build toolchain in the final image.

Default command: `uvicorn disp.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'`.

### 23.2 `docker-compose.yml`

Four services. No identity provider, no auth proxy, no Redis.

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: disp_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?required}
      POSTGRES_DB: disp_db
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U disp_user"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  api:
    build: .
    env_file: .env
    depends_on:
      postgres: {condition: service_healthy}
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/live').status==200 else 1)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    restart: unless-stopped
    labels:
      - traefik.enable=true
      - traefik.http.routers.disp.rule=Host(`${PUBLIC_HOST}`)
      - traefik.http.routers.disp.tls.certresolver=le
      - traefik.http.services.disp.loadbalancer.server.port=8000

  worker:
    build: .
    command: ["python", "-m", "disp.worker"]
    env_file: .env
    depends_on:
      postgres: {condition: service_healthy}
    restart: unless-stopped

  traefik:
    image: traefik:v3.2
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.web.address=:80
      - --entrypoints.websecure.address=:443
      - --entrypoints.web.http.redirections.entrypoint.to=websecure
      - --certificatesresolvers.le.acme.email=${ACME_EMAIL}
      - --certificatesresolvers.le.acme.storage=/letsencrypt/acme.json
      - --certificatesresolvers.le.acme.httpchallenge.entrypoint=web
    ports: ["80:80", "443:443"]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - letsencrypt:/letsencrypt
    restart: unless-stopped

volumes:
  pgdata:
  letsencrypt:
```

Migrations and schema application are explicit one-shot commands, never part of container startup:

```
docker compose run --rm api ./dev migrate
docker compose run --rm api procrastinate --app=disp.core.scheduler.app schema --apply
docker compose run --rm api disp-admin seed-admin --email you@example.com --display-name "You"
```

### 23.3 Backups

`docs/operations.md` MUST document, and the repo MUST include as `scripts/backup.sh`:

- Nightly `pg_dump -Fc` to a timestamped file.
- Retention: 7 daily, 4 weekly.
- Off-host copy (S3 or rsync), with the destination configurable.
- **A restore procedure that has been executed at least once**, documented step by step.
- An explicit warning that `DISP_SETTINGS_KEY` must be backed up separately and that losing it makes every stored notification credential unrecoverable, while losing `DISPJWT_SECRET` only invalidates outstanding access tokens.

---

## 24. Developer tooling

`./dev` is an executable bash script with `set -euo pipefail` implementing:

| Command | Action |
|---|---|
| `./dev up` | `docker compose up -d` |
| `./dev down` | `docker compose down` |
| `./dev migrate [branch]` | Upgrade all branches, or one |
| `./dev makemigration <branch> "<msg>"` | Autogenerate a revision |
| `./dev test [args…]` | `pytest` with coverage gates |
| `./dev lint` | `ruff check` + `ruff format --check` + `mypy src` |
| `./dev fmt` | `ruff format` + `ruff check --fix` |
| `./dev shell` | `psql` into the dev database |
| `./dev seed` | Seed an admin and three sample notes for local work |
| `./dev openapi` | Write `openapi.json` to the repo root |

`ruff` configuration: line length 100; rule sets `E, F, I, N, UP, B, S, A, C4, DTZ, RUF`; `S101` ignored under `tests/`.

`mypy`: `strict = true` for `src/disp/core/`, default strictness elsewhere; `disallow_untyped_defs = true` everywhere. The build fails on any error.

### 24.1 Required documentation

- `README.md` — what this is, quickstart (clone → `.env` → `./dev up` → migrate → seed admin → `disp login`), the architecture in one diagram, and where to read more.
- `docs/adding-a-module.md` — a four-step recipe with a complete, copy-pasteable minimal module, plus the rules a module must obey (own schema, own migration branch, no cross-module imports, auth via the three public names only).
- `docs/auth.md` — the credential types, their lifetimes, the rotation and reuse-detection behaviour, the accepted 15-minute revocation window for access tokens, and the four-step procedure for adopting an external OIDC provider later.
- `docs/operations.md` — backups, restore drill, key rotation, log locations, health endpoints.

---

## 25. Acceptance criteria

The implementation is complete when every item below is demonstrably true.

**Build and run**
1. `docker compose up -d` starts exactly four containers: `postgres`, `api`, `worker`, `traefik`. No identity provider, no auth proxy, no Redis.
2. `./dev migrate` applies both branches; `alembic_version_core` and `alembic_version_notes` both exist and hold one row each.
3. `disp-admin seed-admin` creates the first admin and refuses to run a second time.
4. `GET /health` returns `200` with `status: "ok"` and `modules: ["notes"]`.

**Plug-in mechanism**
5. The `notes` module required zero edits to any file under `src/disp/core/`.
6. The `hello` fixture module appears in the manifest and renders a tile with no platform changes (§22.4).
7. Every failure mode in §9.1 aborts startup with a message naming the module and the rule.

**Auth**
8. Login, refresh rotation, logout, invite acceptance, PAT creation, and password change all behave exactly as §10 specifies.
9. Refresh-token replay revokes the family and returns `401 core.auth.refresh_token_reused`.
10. A PAT and an access token for the same user resolve to equivalent `CurrentUser` values.
11. A PAT cannot create a PAT or change a password.
12. Unknown-email and wrong-password logins are indistinguishable.
13. `src/disp/core/auth/__init__.py` exports exactly the five names in §10.1, and the boundary test in §22.5 passes.
14. `oidc.py` exists, is documented, is never called, and raises `NotImplementedError`.

**Authorization**
15. Creating a note grants OWNER; a second user cannot read it; sharing `read` permits reads and forbids writes.
16. An unreadable resource returns `404`, never `403`.

**Platform services**
17. `NoteCreated` reaches its subscriber; a raising handler does not break publication.
18. The daily planner is registered as periodic and runs in the worker.
19. `notifier.send` defers a job; delivery with no channels logs `no_channels` without raising; Apprise URLs never appear in logs.
20. Settings secrets are encrypted at rest and masked in API responses.

**API quality**
21. Every error response is `application/problem+json` with a `code` from Appendix A and a `request_id`.
22. Every route has an explicit, unique `operation_id`; `./dev openapi` produces a document that `openapi-python-client` and `@hey-api/openapi-ts` both consume without warnings.
23. Cursor pagination over 50 notes yields each note exactly once across pages.
24. Rate limits fire as specified and return `429` with `Retry-After`.

**CLI**
25. `disp login` → `disp notes add "hello"` → `disp notes list` → `disp dashboard` all succeed against a running server.
26. `echo "piped" | disp notes add` creates a note.
27. `disp notes list --json | jq '.items[0].id'` works.
28. Exit codes match §19.3 for auth, network, not-found, and server-error cases.
29. The config file is `0600` and contains no password.

**Quality gates**
30. `./dev lint` passes with zero findings.
31. `./dev test` passes with ≥ 85 % overall and ≥ 95 % on `core/auth/`.
32. No `TODO`, `FIXME`, `pass  # implement`, or `NotImplementedError` remains in shipped code, except the documented `oidc.py` stub.
33. All four documents in §24.1 exist and are accurate against the delivered code.

---

## 26. Out of scope

The implementer MUST NOT build: any web UI; the plants, habits, or shopping-list modules; email delivery; password reset by email; TOTP or WebAuthn; OIDC or SAML; audit-log UI; multi-tenancy; Kubernetes manifests; CI pipeline definitions; a Textual TUI (the Typer CLI only). Adding any of these is a specification violation.

---

## Appendix A — Error code registry

### Naming (normative)

Every `code` is **three segments**: `<realm>.<subsystem>.<error>`.

- `realm` is `core` for anything the backbone owns, `modules` for anything a module owns.
- `subsystem` is the core subsystem (`auth`, `acl`, `pagination`, `dashboard`, `settings`, `platform`)
  or the module's domain (`notes`, `plants`).
- `platform` is the subsystem for codes raised by the exception handlers themselves (§17.4), which
  belong to no domain.

Enforced at construction by `ERROR_CODE_RE` in `src/disp/core/errors.py`:

```
^(core|modules)\.[a-z][a-z0-9_]{1,31}\.[a-z][a-z0-9_]{1,63}$
```

This is deliberately **not** `KEY_RE` (§8.1), the platform's other dotted namespace — tile keys, job
names, notification types — which has exactly two segments. The two were indistinguishable on sight
until the segment count separated them: `modules.notes.not_found` was an error code and `notes.latest` a tile
key, and nothing but context said which. See `milestones/server/M21-error-code-namespace.md`.

### Registry

Every `core.*` code the API may emit. New codes require a specification amendment.

**Module-owned codes are registered in the module's own specification**, not here — see
`src/disp/modules/plants/TECHNICAL-SPEC.md` §18 for `modules.plants.*`. The `modules.notes.*` codes
appear below because `notes` is specified in this document (§18), not because module codes belong in
the backbone registry.

| Code | Status | Meaning |
|---|---|---|
| `core.auth.missing_credentials` | 401 | No `Authorization` header |
| `core.auth.malformed_credentials` | 401 | Header is not `Bearer <token>` |
| `core.auth.invalid_credentials` | 401 | Wrong email or password |
| `core.auth.invalid_token` | 401 | JWT failed validation or user missing |
| `core.auth.token_expired` | 401 | Access token or PAT expired |
| `core.auth.token_revoked` | 401 | PAT revoked |
| `core.auth.invalid_refresh_token` | 401 | Refresh token unknown |
| `core.auth.refresh_token_expired` | 401 | Refresh token past expiry |
| `core.auth.refresh_token_reused` | 401 | Rotated token replayed; family revoked |
| `core.auth.csrf_required` | 403 | `X-Requested-With` missing |
| `core.auth.account_disabled` | 403 | `is_active` false |
| `core.auth.admin_required` | 403 | Admin-only route |
| `core.auth.pat_cannot_mint` | 403 | PAT tried to create a PAT |
| `core.auth.pat_insufficient` | 403 | PAT used on an access-token-only route |
| `core.auth.password_policy` | 422 | New password rejected |
| `core.auth.user_exists` | 409 | Email already registered |
| `core.auth.invite_pending` | 409 | Pending invite exists for that email |
| `core.auth.invite_used` | 409 | Invite already accepted |
| `core.auth.invite_not_found` | 404 | Invite token unknown |
| `core.auth.invite_expired` | 410 | Invite past expiry |
| `core.acl.forbidden` | 403 | Permission rank too low |
| `core.pagination.invalid_cursor` | 400 | Cursor could not be decoded |
| `core.dashboard.tile_not_found` | 404 | Unknown tile key |
| `core.settings.domain_not_found` | 404 | No settings panel for that domain |
| `core.settings.decryption_failed` | 500 | Wrong or rotated `SETTINGS_KEY` — see the note below |
| `core.platform.rate_limited` | 429 | Rate limit exceeded |
| `core.platform.validation_error` | 422 | Request schema violation |
| `core.platform.http_error` | 4xx/5xx | A bare `HTTPException` reached the handler (§17.4) |
| `core.platform.internal_error` | 500 | Unhandled exception |
| `modules.notes.not_found` | 404 | Note absent or not readable |
| `modules.notes.user_not_found` | 404 | Share target email unknown |
| `modules.notes.cannot_share_with_self` | 400 | Share target is the caller |

> **`core.settings.decryption_failed` is registered but never raised.** `settings_store.py` logs a
> `settings_decryption_failed` *event* on a decryption failure but emits no problem response with this
> code, while the web client carries a branch for it (`clients/web/src/api/queries.ts`). Found during
> the M21 rename and left as-is: making the registry honest means either raising it or deleting it, and
> that is a behaviour change, not a rename. Resolve it deliberately rather than by accident.

> **`core.platform.http_error` was emitted but unregistered** until M21 — `errors.py`'s `HTTPException`
> handler has always produced it. It is listed now so the registry's opening claim is true.

---

## Appendix B — Worked examples

### B.1 Login

```http
POST /api/auth/login HTTP/1.1
Content-Type: application/json

{"email":"me@example.com","password":"correct horse battery staple"}
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: disp_refresh=Xk3…; Path=/api/auth; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000
X-Request-ID: 01JF3KXYZ

{"access_token":"eyJhbGciOiJIUzI1NiIs…","token_type":"bearer","expires_in":900,
 "user":{"id":"6f1c…","email":"me@example.com","display_name":"Me","is_admin":true}}
```

### B.2 Creating a note with a PAT

```http
POST /api/notes HTTP/1.1
Authorization: Bearer disp_pat_7Qk2…
Content-Type: application/json

{"title":"Groceries","body":"milk, bread","pinned":true}
```

```http
HTTP/1.1 201 Created
Location: /api/notes/9a2f1c74-3d6e-4a1b-9f02-1c4e5a6b7d8e

{"id":"9a2f1c74-3d6e-4a1b-9f02-1c4e5a6b7d8e","title":"Groceries","body":"milk, bread",
 "pinned":true,"created_at":"2026-07-24T09:12:03Z","updated_at":"2026-07-24T09:12:03Z"}
```

### B.3 A tile response

```json
{
  "key": "notes.latest",
  "title": "Latest notes",
  "count": 12,
  "items": [
    {"id":"9a2f1c74-…","primary":"Groceries","secondary":"pinned",
     "timestamp":"2026-07-24T09:12:03Z","done":null,"href":"/api/notes/9a2f1c74-…"}
  ],
  "actions": [
    {"id":"quick_add","label":"Add note","method":"POST","path":"/api/notes",
     "body_schema":{"type":"object","required":["body"],
                    "properties":{"body":{"type":"string"}}}}
  ],
  "empty_text": "No notes yet",
  "generated_at": "2026-07-24T09:15:00Z"
}
```

### B.4 An error response

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{"type":"about:blank","title":"Forbidden","status":403,
 "detail":"You do not have write access to this note.",
 "instance":"/api/notes/9a2f1c74-…","code":"core.acl.forbidden",
 "request_id":"01JF3KXYZ"}
```

### B.5 A minimal module (the `hello` fixture, complete)

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

This is the entire surface area required of a module. Anything more is that module's own business.

---

*End of specification.*
