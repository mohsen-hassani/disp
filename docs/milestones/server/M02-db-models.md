# M2 — db.py + core/models.py

**Status:** Complete

**Scope:** Engine factory (`pool_size=10`, `max_overflow=5`, `pool_pre_ping=True`), `async_session_maker` (`expire_on_commit=False`), `Base` with naming convention, `get_session()` dependency, `session_scope()` for background tasks, and ORM models for all seven `core` schema tables.

Covers TECHNICAL-SPEC.md §6 (Database conventions and DDL).

---

## §6.1 Conventions

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

## §6.2 Schema `core` — DDL

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

`uq_settings_scope` relies on `NULLS NOT DISTINCT`, available in PostgreSQL 15+. PostgreSQL 16 is the pinned version, so this is valid. (Implementation note: SQLAlchemy 2.0's `Index(..., postgresql_nulls_not_distinct=True)` was used.)

## §6.3 Session management

- The async engine MUST be created with `pool_size=10`, `max_overflow=5`, `pool_pre_ping=True`.
- `async_session_maker` MUST use `expire_on_commit=False`.
- A FastAPI dependency `get_session()` MUST yield one session per request, commit on success, roll back on exception, and always close.
- Background tasks MUST create their own session via an async context manager; they MUST NOT reuse a request session.
