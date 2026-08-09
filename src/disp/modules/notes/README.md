# `notes` module

The demo module shipped with DISP. Quick personal notes with pinning, full-text search, and
sharing. It exists to exercise the full plug-in surface — HTTP CRUD, a dashboard tile, a scheduled
cleanup job, an event subscription — so you have a real, working example to copy when writing your
own module. Its implementation quality is held to the same standard as the backbone; see
[`docs/adding-a-module.md`](../../../../docs/adding-a-module.md) for the general four-step recipe
this module follows.

## What it does

- **CRUD** on notes: title (optional), body (required), a `pinned` flag.
- **Full-text search** over title + body via Postgres `to_tsvector`/`plainto_tsquery` (simple
  config, GIN-indexed).
- **Cursor pagination**, ordered `pinned DESC, created_at DESC, id DESC`.
- **Sharing**: the owner can grant another user `read` or `write` access to a note.
- **Soft delete**: `DELETE` sets `deleted_at` rather than removing the row; a scheduled job
  hard-deletes anything soft-deleted more than 30 days ago.
- **A dashboard tile** (`notes.latest`) showing the 5 most recent notes plus a quick-add action.
- **One domain event** (`NoteCreated`) with a handler that logs at `INFO` — proving the event bus
  is exercised end to end, not because anything downstream currently depends on it.

## Data model

One table, `notes.notes` (own Postgres schema, own Alembic branch — see
[`migrations/versions/0001_notes_initial.py`](migrations/versions/0001_notes_initial.py)):

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` | PK, `gen_random_uuid()` |
| `user_id` | `uuid` | Owner. **No FK to `core.users`** — modules must not create cross-schema foreign keys (spec §6.1); ownership is enforced via ACL grants, not a database constraint. |
| `title` | `text`, nullable | 1–200 chars when present |
| `body` | `text` | 1–20000 chars |
| `pinned` | `boolean` | default `false` |
| `created_at` / `updated_at` | `timestamptz` | |
| `deleted_at` | `timestamptz`, nullable | soft-delete marker |

Access control goes through the platform's ACL (`disp.core.auth`), not a `notes.notes` column: on
creation the owner gets an `OWNER` grant on resource `("notes.note", <note id>)`; `share_note`
grants `read`/`write` to another user by email. `list_notes` calls `readable_ids()` once to get
every note the caller can see, then filters — not a per-row permission check. See
[`service.py`](service.py)'s `_authorize()` for the exact 404-vs-403 rule: a caller who can't even
read a note gets `404 modules.notes.not_found` (existence hidden); a caller who can read it but lacks the
permission for the specific action gets `403 core.acl.forbidden`.

## HTTP API

Base path `/api/notes`, tag `notes`. Every route requires authentication.

| Method | Path | Operation id | Notes |
|---|---|---|---|
| `GET` | `` | `notes_list` | `limit` (1–100, default 20), `cursor`, `q` (full-text, ≤200 chars), `pinned` |
| `POST` | `` | `notes_create` | Body: `{title?, body, pinned?}`. Returns `201` with a `Location` header. |
| `GET` | `/{note_id}` | `notes_get` | |
| `PATCH` | `/{note_id}` | `notes_update` | Partial update, any subset of `title`/`body`/`pinned` |
| `DELETE` | `/{note_id}` | `notes_delete` | Soft delete, `204`. Repeating on an already-deleted note is `404`. |
| `POST` | `/{note_id}/share` | `notes_share` | Body: `{email, permission: "read"\|"write"}`. Owner only. |

Error codes worth knowing: `modules.notes.not_found` (404), `core.acl.forbidden` (403, readable but not
writable), `modules.notes.cannot_share_with_self` (400), `modules.notes.user_not_found` (404, share target has no
account). Full request/response schemas are in [`schemas.py`](schemas.py) and the live OpenAPI doc
(`./dev openapi`, or `GET /openapi.json` against a running server).

## Dashboard tile

`notes.latest` (medium, refreshes every 120s): shows a count of readable notes, the 5 most recent
as `TileItem`s (`primary` = title or a 60-char body preview, `secondary` = `"pinned"` when pinned,
`href` = `/api/notes/{id}`), and one action — `quick_add`, a `POST /api/notes` with a minimal
`{body}` schema for one-field note creation straight from the dashboard. See
[`tiles.py`](tiles.py).

## Scheduled job

`notes.purge_deleted` runs daily at 03:30 (cron `30 3 * * *`) and hard-deletes any row where
`deleted_at` is more than 30 days in the past. Registered in [`__init__.py`](__init__.py) via
`platform.scheduler.task(...)`; runs in the worker process (`python -m disp.worker`), not the API
process.

## Using it: the `disp` CLI

```sh
disp notes list                                # table view
disp notes list --pinned --query "groceries"   # filter + search
disp notes list --all --json | jq '.items[0]'  # page through everything, raw JSON

disp notes add "Pick up milk" --pin            # create with an inline body
echo "Longer note text" | disp notes add       # create from stdin
disp notes add                                 # create by opening $EDITOR

disp notes show a1b2c3d4                       # accepts a full id OR an unambiguous prefix (≥4 chars)
disp notes edit a1b2c3d4 --pin                  # patch just the pinned flag
disp notes edit a1b2c3d4                        # no flags: opens $EDITOR pre-filled with the body
disp notes rm a1b2c3d4 --yes                    # soft-delete, skipping the confirmation prompt
disp notes share a1b2c3d4 --email a@b.com --permission read
```

Every command talks to the HTTP API exactly like any other client (`src/disp/cli/commands/notes.py`)
— there's no special CLI-only code path into the module. `disp notes show`/`edit`/`rm`/`share`
resolve a short id prefix to a full UUID by fetching every note and matching `startswith()`; an
ambiguous or too-short prefix (under 4 characters) is rejected rather than guessing.

## Using it: HTTP directly

```sh
# Assumes a session cookie/bearer token from `disp login`, or curl with -H "Authorization: Bearer <PAT>"
curl -s http://localhost:8000/api/notes -H "Authorization: Bearer $TOKEN" | jq

curl -s -X POST http://localhost:8000/api/notes \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"body": "Pick up milk", "pinned": true}'
```

## Developing

- **Layout**: `manifest.py` (what the module contributes), `models.py` (SQLAlchemy ORM, schema
  `notes`), `schemas.py` (Pydantic request/response models), `service.py` (business logic — auth
  checks, pagination, the actual DB queries), `router.py` (thin FastAPI routes calling into
  `service.py`), `tiles.py` (dashboard tile provider), `events.py` (domain events),
  `__init__.py` (the `PlatformModule` implementation: `register()`, `api_router()`,
  `tile_provider()`, and the `get_module()` factory the registry discovers).
- **Boundary rules** (enforced by `tests/core/test_boundaries.py`, not just convention — see the
  root [`CLAUDE.md`](../../../../CLAUDE.md)): this module may not import from another module, may
  not import `disp.core.app`, may only import `get_session`/`session_scope`/`Base` from
  `disp.core.db`, and may only use auth's public surface (`CurrentUser`, `Permission`, `can`,
  `current_user`, `grant`, `list_grants`, `readable_ids`, `require`, `require_admin`, `revoke`).
- **Migrations**: own Alembic branch (`notes`), own Postgres schema. New migration:
  `./dev makemigration notes "<message>"` from the repo root, then `./dev migrate notes` (or
  `./dev migrate` for every branch) to apply it.
- **Background session outside a request**: the scheduled job needs its own DB session since it
  doesn't run inside a FastAPI request — see `__init__.py`'s `_purge_deleted`, which calls
  `session_scope()` with no arguments (it lazily builds its own engine/session-maker from settings
  on first use in a background context).
- **Tests**: [`tests/modules/test_notes.py`](../../../../tests/modules/test_notes.py) exercises the
  service layer directly (auth, pagination, search, sharing, the 404-vs-403 distinction, the purge
  job) plus the full HTTP surface via `TestClient`. Run just this module's tests with
  `./dev test tests/modules/test_notes.py`; run everything with `./dev test`.
- **Full build history**: [`milestones/server/M13-notes-module.md`](../../../../milestones/server/M13-notes-module.md)
  documents every design decision and contract gap found while building this module (e.g. why
  `Base` had to be added to the auth boundary's allowed imports, how the 3-key sort survives
  generic cursor pagination, why resolving a share target's email is not a boundary violation).
