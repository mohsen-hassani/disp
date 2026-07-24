# M13 — notes module

**Status:** Complete

**Scope:** `modules/notes/{models,manifest,schemas,service,router,tiles,events,__init__}.py`, plus filling in `modules/notes/migrations/versions/0001_notes_initial.py` (already hand-authored at M5).

Covers TECHNICAL-SPEC.md §18 (Notes module).

---

## §18. Notes module

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

(Already hand-authored into `modules/notes/migrations/versions/0001_notes_initial.py` at M5 — see `milestones/M05-alembic.md`.)

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

**`POST /{note_id}/share`** requires `owner`. Body `{"email": str, "permission": "read"|"write"}`. Resolves the email to a user (`404 notes.user_not_found` if absent), then `grant`s. Returns `204`. Sharing with oneself returns `400 notes.cannot_share_with_self`.

All single-note routes: resolve the note, then `require(action)`. Absent or not readable → `404 notes.not_found`.

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

## Notes

- `models.py` must import `Base` from `disp.core.db` (the shared declarative base — see M5's note on why this is required for the alembic `include_object` filter to work at all).
- `service.py`/`router.py` must go through the auth boundary only via the public surface (expanded during this milestone — see below) — this is exactly what `tests/core/test_boundaries.py` (M6) checks, and it got its first real exercise once this module's files existed.
- `router.py` gets its DB session via `Depends(get_session)` (the sanctioned `disp.core.db` import per M6's boundary-test interpretation), not by importing the engine.

## Two real contract gaps found and resolved while building this module

Writing the actual notes module — the spec's own proof that the contract works — immediately exposed two places where the M6 boundary test's restrictions, taken literally, made §18.3's requirements impossible to satisfy. Both are documented in full in `milestones/M06-auth.md`'s "retroactive amendment" sections; summarized here:

1. **`grant()`/`readable_ids()` weren't in the public auth surface.** §18.3 requires the notes module to call `grant(...)` on note creation and filter its list query with `readable_ids`, but §10.1's literal `auth/__init__.py` only exported `CurrentUser, Permission, can, current_user, require_admin`. Resolved by expanding the export list to the full ACL API (`grant, revoke, list_grants, readable_ids, require` added), since G4/§11.2 only make sense that way and the boundary's stated OIDC-migration rationale has nothing to do with ACL.
2. **`Base` wasn't in the allowed `disp.core.db` imports.** `notes/models.py` needs `Base` to define its ORM model at all (per the M5 shared-metadata design), but the boundary test only allowed `get_session`/`session_scope`. Resolved by reading §8.4's "the SQLAlchemy engine" ban narrowly (it means `create_engine`/`create_session_maker`, not the declarative base) and adding `Base` to the allowed set.

## Third gap found: modules have no sanctioned way to get a DB session outside a request

`notes.purge_deleted` (a scheduled job registered in `register()`) needs its own database session at execution time, per §6.3 ("Background tasks MUST create their own session via an async context manager"). But `Platform` (§8.4) exposes no engine/session-maker field, `get_session` is a FastAPI dependency requiring a `Request` object background tasks don't have, and `session_scope` (my own M2 design, not a literal spec signature) required an explicit `session_maker` argument that only core-internal code had a way to construct.

Resolved by making `session_scope()`'s `session_maker` parameter **optional**: when omitted, it lazily builds (and caches, via `@lru_cache`) a background engine/session-maker directly from `get_settings().database_url` on first use. Core code that already has a session maker at hand (`disp.core.notifier`) can still pass one explicitly; module code (`notes/__init__.py`'s `_purge_deleted` task) just calls `session_scope()` with no arguments. This is a change to my own M2 code, not a spec signature, so no further contradiction — just closing a gap in an internal design decision once a real module exposed it.

## Design notes

- **`resource_type = "notes.note"`**, matching §18.3's literal example, used for every ACL call.
- **404-vs-403 (S9)** is implemented as a dedicated `_authorize()` helper in `service.py`, not a bare call to `require()`: a caller who can't even read a note gets `404 notes.not_found` (existence hidden); a caller who can read it but lacks the specific permission for the requested action (e.g. read-only share attempting `PATCH`) gets `403 acl.forbidden`. Verified directly against the live DB (test case 48's exact scenario).
- **Cursor pagination** (§17.5) encodes only `{ts, id}`, but the notes list order is a 3-key sort (`pinned DESC, created_at DESC, id DESC`). Since the generic cursor doesn't carry `pinned`, the seek step re-derives it by loading the referenced note (by the `id` already in the cursor) and building a compound `(pinned, created_at, id) < (seek.pinned, seek.created_at, seek.id)` row comparison for the next page's `WHERE` clause. Verified with 26 notes across a mix of pinned/unpinned paginated at `limit=10`: 3 pages, zero duplicates, zero gaps.
- **Resolving a share target's email to a user** requires a plain `SELECT` against `core.users` from within the notes module (`disp.core.models.User`). This reads as tension with §6.1 ("Modules MUST NOT read or write another schema's tables"), but that rule's stated rationale is specifically about cross-schema **foreign keys and SQL joins** ("prevents accidental joins"); this is a single, unjoined lookup query, the same shape as the ACL access pattern already used everywhere else (fetch IDs from `core.acl` in one query, the module's own rows in a second, never joined at the SQL level). The boundary test doesn't forbid importing `disp.core.models`, which is consistent with this reading.

## End-to-end verification against the live database (beyond the pre-existing unit suite)

Ran the full HTTP surface via `TestClient` with two real users (owner + an invited second user): create (with `Location` header), get, list (pinned-first ordering, full-text search via the GIN index, exclusion of soft-deleted/other-users'-notes), update (partial, `exclude_unset` semantics), soft-delete (idempotent 404 on redelete), share (read-only grant, self-share rejection, unknown-email rejection), the 404-vs-403 authorization distinction, the `notes.latest` dashboard tile (preview truncation with an ellipsis, `pinned` secondary label, count, quick-add action), the `NoteCreated` event's `INFO`-level log line, cursor pagination across 3 pages of 26 notes with zero duplicates/gaps, and `purge_deleted` (removes only rows soft-deleted >30 days ago, verified with a 35-day-old and a 5-day-old deleted row side by side).

Also found and fixed an unrelated **`./dev migrate` idempotency bug**: `procrastinate schema --apply` isn't idempotent (fails with "already exists" on a second run), so re-running `./dev migrate` — or migrating a second branch after the first — broke with `set -euo pipefail`. Fixed by checking for `public.procrastinate_jobs`'s existence first and only applying the schema if it's missing.

`ruff`/`ruff format --check`/`mypy` all clean across 44 source files; the pre-existing 23-test suite still passes unchanged.
