# M5 — Alembic scaffolding

**Status:** Complete (functional verification against a live Postgres deferred to M12)

**Scope:** `alembic.ini` (`[core]`/`[notes]` sections), `core/migrations/env.py` (real implementation), `core/migrations/script.py.mako`, hand-authored `core/migrations/versions/0001_core_initial.py`, `modules/notes/migrations/env.py` (thin re-export) + its own `script.py.mako`, `modules/notes/migrations/versions/0001_notes_initial.py`.

Covers TECHNICAL-SPEC.md §7 (Migrations), plus the notes-schema DDL from §18.2 (needed for the notes branch's initial revision, even though the notes module itself isn't built until M13).

---

## §7. Migrations

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

1. Read `MYSTUFF_DATABASE_URL_SYNC` from the environment; never hard-code a URL.
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
- `notes` branch, revision 1: `notes` schema and the table in §18.2 (see below).

## §18.2 Schema `notes` — DDL (needed for the notes branch's revision 1)

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

## Implementation notes

- The spec's `alembic.ini` snippet gives `notes` a *different* `script_location` than `core` (`src/disp/modules/notes/migrations` vs `src/disp/core/migrations`). Since Alembic looks for `script.py.mako` inside whatever `script_location` is configured, this means the notes branch needs **its own copy** of `script.py.mako` (identical content), even though the repo tree in §4 only itemizes one `script.py.mako` under `core/migrations`. Added as a reasonable gap-fill, same category as the `scripts/backup.sh` omission.
- `modules/notes/migrations/env.py` is a one-line re-export: `from disp.core.migrations.env import *  # noqa: F403` — this re-executes the real `env.py` in its own module namespace, and Alembic's shared `context.config` (with `config_ini_section == "notes"`) is still the one in scope, so branch detection works correctly.
- `env.py` imports **only the active branch's own models module** (`disp.core.models` for `core`, `disp.modules.notes.models` for `notes`) rather than all branches' models — this alone keeps `Base.metadata` scoped correctly per branch; the `include_object` schema filter is a defense-in-depth net on top of that.
- Revision 1 for both branches is hand-authored raw SQL (`op.execute(...)`) reproducing the DDL verbatim, not autogenerated, per §7.4.
- Functional verification (`./dev migrate` against a live container) happens at M12, once Postgres is up.
