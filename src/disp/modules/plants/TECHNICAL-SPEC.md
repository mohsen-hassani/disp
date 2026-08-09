# `plants` Module — Technical Specification

**Document type:** As-built specification
**Version:** 1.0
**Status:** Implemented
**Scope:** `src/disp/modules/plants/`, its Alembic branch, and the `clients/web` screens that consume it

---

## How to read this document

Unlike [`TECHNICAL-SPEC.md`](../../../../TECHNICAL-SPEC.md), which was written **before** the
platform and is normative-prospective, this document was written **from** a finished
implementation. It describes what the code does and, more importantly, *why each decision went the
way it did*.

It is still normative going forward: code that contradicts a **MUST** here is either a bug or a
change that requires updating this document in the same commit. Keywords follow RFC 2119.

Where this document and the platform spec disagree, the platform spec wins — this module is a
tenant of the contract in §8 of that document, not an amendment to it.

`README.md` in this directory is the short orientation; this is the complete reference.

---

## Table of Contents

1. [Purpose and non-goals](#1-purpose-and-non-goals)
2. [Domain model](#2-domain-model)
3. [The scheduling invariants](#3-the-scheduling-invariants)
4. [Configuration](#4-configuration)
5. [Schema `plants` — DDL](#5-schema-plants--ddl)
6. [Migrations and branch registration](#6-migrations-and-branch-registration)
7. [Manifest](#7-manifest)
8. [Service layer](#8-service-layer)
9. [Calendar projection](#9-calendar-projection)
10. [HTTP API](#10-http-api)
11. [Photo storage](#11-photo-storage)
12. [Authorization](#12-authorization)
13. [Dashboard tile](#13-dashboard-tile)
14. [Daily reminder job](#14-daily-reminder-job)
15. [Settings panel](#15-settings-panel)
16. [Events](#16-events)
17. [Web client](#17-web-client)
18. [Error code registry](#18-error-code-registry)
19. [Testing](#19-testing)
20. [Operational requirements](#20-operational-requirements)
21. [Known limitations and out of scope](#21-known-limitations-and-out-of-scope)
22. [Appendix A — Worked example](#appendix-a--worked-example)
23. [Appendix B — Files](#appendix-b--files)

---

## 1. Purpose and non-goals

### 1.1 Purpose

Track houseplants and the recurring care each one needs — watering, several distinct fertilizers,
fungicide, repotting, soil changes — and answer one question well:

> **What do I need to do today, and how far behind am I?**

Secondary: a month calendar showing what was actually done in the past and what is scheduled ahead.

### 1.2 Goals

- A plant MUST be creatable from a name alone, with description, care notes, photo and schedule all
  addable later. Adding a plant must not feel like filling in a form.
- Each plant MAY carry an arbitrary number of independently-scheduled recurring actions.
- Falling behind MUST be visible and quantified ("2 days behind"), and MUST self-correct the moment
  the work is done.
- Completed care MUST be preserved as history that later edits cannot rewrite.

### 1.3 Non-goals

- **No plant database or species catalogue.** Care rules are free text the user writes
  (`plant.care_notes`); the module has no opinion about what a Sansevieria needs.
- **No weather, sensors, or automatic watering integration.**
- **No per-interval sharing.** ACL granularity is the plant (§12).
- **No recurrence grammar.** An interval is a fixed number of days. No "every second Tuesday",
  no seasonal cadence, no cron. §21 records why.
- **No in-app notification inbox.** See §14.3.

---

## 2. Domain model

Three tables, all in the `plants` schema.

```
Plant  1 ──── n  CareInterval        "Water, every 15 days, next due 2026-03-16"
  │                    │
  │                    │ (SET NULL on delete)
  └──────── n  CareLog ┘             "Water, due 2026-03-01, done 2026-03-03, 2 days late"
```

| Entity | Answers |
|---|---|
| `Plant` | *What* am I looking after — name, description, free-text care notes, photo |
| `CareInterval` | *What recurs, how often, and when is it next due* |
| `CareLog` | *What did I actually do, and when* — append-only |

### 2.1 The `care_notes` / `CareInterval` split

`plant.care_notes` is prose the user writes for themselves ("bright indirect light, let it dry out
fully between waterings"). It is never parsed. The machine-readable half — what recurs and how
often — lives in `care_interval`, one row per action.

This split is deliberate: attempting to derive a schedule from prose would be both unreliable and
unnecessary, since the user already knows the cadence and can state it in a number.

### 2.2 Why `CareLog.action_name` is a snapshot

`care_log` stores `action_name TEXT` rather than relying on a join to `care_interval.name`, and
`care_log.interval_id` is `ON DELETE SET NULL` rather than `CASCADE`.

Rationale: the calendar shows past months. If renaming "Water" to "Watering" retroactively rewrote
every historical entry, or deleting a retired interval erased the record that it was ever done, the
calendar would be lying about the past. History MUST be immutable against later edits to the
schedule that produced it.

---

## 3. The scheduling invariants

These four rules are the substance of the module. Everything else is plumbing.

### 3.1 Rescheduling anchors to the completion date (the central rule)

> **On completion, `next_due_on` MUST be set to `completed_on + interval_days`.**
> It MUST NOT be derived from the date the action was *due*.

Watering on a 15-day cycle falls due on the 1st. The user does it on the 3rd. The next occurrence is
due on the **18th** (3rd + 15), **not** the 16th (1st + 15).

Rationale: anchoring to the due date makes a user who runs late *permanently* late — every cycle
starts already in deficit, and the error compounds. Anchoring to reality means the schedule
re-baselines itself on each completion. This is also what the physical world does: the plant does
not care when you intended to water it.

The same rule applies when completing **early**: doing it 3 days ahead moves the next occurrence 3
days earlier. There is no notion of "catching up" or of a fixed calendar grid.

### 3.2 Missed occurrences do not accumulate

An interval has exactly **one** `next_due_on`. Being 40 days behind on a 15-day cycle produces one
due item that is 40 days late, **not** two-and-a-bit queued waterings.

Rationale: you water the plant once, not three times. A queue model would create phantom work that
can never be discharged.

### 3.3 Due state is derived, never stored

> **There MUST be no "reminder", "notification", or "due" row.**

Lateness is computed at read time:

```
days_overdue = today - next_due_on
```

| Value | Meaning |
|---|---|
| `< 0` | Not due yet |
| `0` | Due today |
| `> 0` | This many days behind |

Rationale: a stored due-state needs reconciling — after a completion, after a cadence edit, after a
back-dated log, at local midnight. Every one of those is an opportunity to go stale, and a stale
reminder is worse than none. Deriving it makes "correct" the only reachable state, and makes the
dashboard tile accurate the instant an action is marked done.

Cost: every read recomputes. At personal-platform scale (tens of plants, hundreds of intervals) this
is a single indexed query, so the cost is not worth engineering away.

### 3.4 "Today" is local, never UTC

Every date comparison MUST route through `service.today()`:

```python
def today() -> date:
    return datetime.now(ZoneInfo(get_settings().timezone)).date()
```

Rationale: a reminder that rolls over at UTC midnight fires at the wrong local hour for anyone not
on UTC — for `Europe/Amsterdam` in summer, "today" would begin at 02:00. Because this is the single
definition, pinning it is also the only thing a test needs to stub to fix the date
(§19.2).

`reminders.py` deliberately calls `service.today()` through the module rather than importing the
name, so that one stub covers it too.

### 3.5 `last_done_on` is NULL until genuinely completed

Creating an interval with no `last_done_on` computes the first occurrence from *today* but stores
`last_done_on = NULL`.

Rationale: "never done" and "done today" are different facts. Recording a completion that did not
happen would put a false entry into the history the calendar reads. Where a cycle start is needed
before any completion exists (§8.4), it is reconstructed arithmetically instead.

---

## 4. Configuration

Module-owned, in `config.py`. A separate `BaseSettings` with its own prefix — **not** fields on
`disp.core.config.Settings`.

| Variable | Default | Meaning |
|---|---|---|
| `DISP_PLANTS_MEDIA_ROOT` | `var/media/plants` | Directory for photos. Relative paths resolve against the process CWD. |
| `DISP_PLANTS_MAX_IMAGE_BYTES` | `2097152` (2 MiB) | Upload size ceiling. |

Rationale: a module MUST NOT require an edit to `core/` to be installable (§8 of the platform spec).
Adding fields to the core `Settings` would break that.

**Verified compatibility note.** Core `Settings` is `extra="forbid"` with `env_prefix="DISP_"`,
which raises the obvious question of whether `DISP_PLANTS_*` trips it. It does not:
pydantic-settings only collects env vars that map to a declared field, so unknown prefixed vars are
ignored. This was confirmed empirically before the design was committed to, not assumed.

`get_plants_settings()` is `@lru_cache`d. Tests that change the env MUST call `cache_clear()`.

---

## 5. Schema `plants` — DDL

Authoritative target state. `0001_plants_initial` produces exactly this, and
`alembic --name=plants check` reports no drift against `models.py`.

```sql
CREATE SCHEMA IF NOT EXISTS plants;

CREATE TABLE plants.plant (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID        NOT NULL,          -- no FK: see platform spec §6.1
    name               TEXT        NOT NULL,
    description        TEXT,
    care_notes         TEXT,
    image_path         TEXT,                          -- relative to media root, never absolute
    image_content_type TEXT,
    image_updated_at   TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at         TIMESTAMPTZ,
    CONSTRAINT ck_plants_name_len        CHECK (char_length(name) BETWEEN 1 AND 120),
    CONSTRAINT ck_plants_description_len CHECK (description IS NULL OR char_length(description) <= 2000),
    CONSTRAINT ck_plants_care_notes_len  CHECK (care_notes IS NULL OR char_length(care_notes) <= 20000)
);

CREATE INDEX ix_plants_plant_user_created
    ON plants.plant (user_id, created_at DESC) WHERE deleted_at IS NULL;

CREATE TABLE plants.care_interval (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    plant_id      UUID        NOT NULL REFERENCES plants.plant (id) ON DELETE CASCADE,
    name          TEXT        NOT NULL,
    interval_days INTEGER     NOT NULL,
    next_due_on   DATE        NOT NULL,
    last_done_on  DATE,                               -- NULL until genuinely completed (§3.5)
    active        BOOLEAN     NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_plants_interval_name_len   CHECK (char_length(name) BETWEEN 1 AND 80),
    CONSTRAINT ck_plants_interval_days_range CHECK (interval_days BETWEEN 1 AND 3650)
);

CREATE INDEX ix_plants_interval_plant ON plants.care_interval (plant_id);
CREATE INDEX ix_plants_interval_due   ON plants.care_interval (next_due_on) WHERE active;

CREATE TABLE plants.care_log (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    plant_id     UUID        NOT NULL REFERENCES plants.plant (id) ON DELETE CASCADE,
    interval_id  UUID                 REFERENCES plants.care_interval (id) ON DELETE SET NULL,
    user_id      UUID        NOT NULL,
    action_name  TEXT        NOT NULL,                -- snapshot, see §2.2
    due_on       DATE        NOT NULL,
    completed_on DATE        NOT NULL,
    days_late    INTEGER     NOT NULL,                -- completed_on - due_on; negative if early
    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_plants_log_action_name_len CHECK (char_length(action_name) BETWEEN 1 AND 80),
    CONSTRAINT ck_plants_log_note_len        CHECK (note IS NULL OR char_length(note) <= 2000)
);

CREATE INDEX ix_plants_log_plant_completed ON plants.care_log (plant_id, completed_on DESC);
CREATE INDEX ix_plants_log_user_completed  ON plants.care_log (user_id,  completed_on DESC);
```

### 5.1 Notes on the DDL

- **Intra-schema FKs are used and correct.** The platform's no-FK rule (§6.1) forbids FKs *across*
  schemas. `care_interval → plant` is within `plants`, so it is a normal FK with `CASCADE`.
- `plant.user_id` and `care_log.user_id` are bare UUIDs with no FK to `core.users`, per §6.1.
- `ix_plants_interval_due` is partial on `active` because every due query filters `active = true`.
- `days_late` is stored rather than recomputed, because `due_on` is also stored: keeping both makes
  the log self-describing without needing the interval row (which may be gone — §2.2).
- Soft delete exists on `plant` only. Intervals and logs are hard-deleted or cascade.

---

## 6. Migrations and branch registration

The module owns Alembic branch `plants`, version table `alembic_version_plants` in schema `plants`.

Registration is **one** entry in `alembic.ini`:

```ini
[plants]
script_location = src/disp/modules/plants/migrations
version_locations = src/disp/modules/plants/migrations/versions
version_table = alembic_version_plants
version_table_schema = plants
```

### 6.1 A core change this module required, once

Before this module, `src/disp/core/migrations/env.py` held a hardcoded `BRANCH_MODELS` dict mapping
each branch to its models module, and `./dev migrate` had a hardcoded module allow-list. Both meant
adding a module *did* require editing `core/` — contradicting the platform's own promise and
`tests/core/test_plugin_proof.py`.

That was fixed rather than extended:

- `env.py` now resolves models **by convention** — `_models_module(branch)` returns
  `disp.modules.<branch>.models` for anything that is not `core`.
- `./dev migrate` now upgrades every module shipping a `migrations/versions/` directory, discovered
  from the filesystem.

Consequence: a future module needs **only** the `alembic.ini` section. Two places outside the
runtime still enumerate branches and need a line each — `tests/conftest.py` and
`docker-compose.e2e.yml`'s `migrate` service.

---

## 7. Manifest

```python
MANIFEST = ModuleManifest(
    domain="plants",
    name="Plants",
    version="1.0.0",
    description="Plant care schedules with recurring watering, feeding and repotting reminders.",
    dependencies=(),
    tiles=(TileSpec(key="plants.due", title="Plant care", size=MEDIUM,
                    refresh_seconds=300, order=20),),
    settings_panels=(SettingsPanelSpec(key="plants.reminders", schema_model=PlantsSettingsSchema,
                                       scope="user"),),
    scheduled_jobs=(ScheduledJobSpec(name="plants.daily_check", cron="0 7 * * *"),),
    notification_types=(NotificationTypeSpec(key="plants.care_due", ...),),
)
```

Unlike `notes.reminder`, the `plants.care_due` notification type **is** sent — by §14.

---

## 8. Service layer

`service.py` holds all business logic. `router.py` is a thin translation layer and MUST stay that
way.

### 8.1 `today()`

§3.4. The single definition of the current date.

### 8.2 Listing plants

`list_plants(session, user, *, limit, cursor, q)` → `Page[PlantOut]`.

- Readable set comes from `readable_ids()` **once**, then a single `WHERE id IN (...)` — never a
  per-row `can()` check.
- Excludes `deleted_at IS NOT NULL`.
- `q` is a case-insensitive `ILIKE '%q%'` on `name` only. Deliberately not full-text: plant names
  are one or two words, and a GIN index would be more machinery than the problem needs.
- Ordering `created_at DESC, id DESC`; cursor pagination per platform §17.5.
- Fetches `limit + 1` rows to compute `has_more`.

**Rollups.** `PlantOut` carries `due_count`, `max_days_overdue` and `next_due_on`, computed across
the plant's *active* intervals. All intervals for the whole page are fetched in **one** query
(`_intervals_for`) and aggregated in Python, so a list of N plants costs 2 queries, not N+1.

### 8.3 Creating an interval

`add_interval(...)` with `CareIntervalCreate{name, interval_days, last_done_on?}`:

```
effective_last_done = last_done_on ?? today()
next_due_on         = effective_last_done + interval_days
stored last_done_on = last_done_on          (NULL if omitted — §3.5)
```

`last_done_on` in the future → `400 modules.plants.future_date`.

The optional `last_done_on` is what makes "I already watered it 20 days ago" produce a schedule
that is correctly 5 days overdue, instead of one silently 20 days out of phase.

### 8.4 Changing the cadence

When `interval_days` changes and `next_due_on` is **not** explicitly supplied in the same request,
`next_due_on` MUST be re-derived so the pending occurrence reflects the new cadence:

```
anchor      = last_done_on ?? (next_due_on - old_interval_days)     # captured BEFORE mutation
next_due_on = anchor + new_interval_days
```

The fallback branch exists because of §3.5 — a never-completed interval has no `last_done_on`, and
leaving its date computed under the abandoned cadence is a silent wrong answer. Working backwards
from `next_due_on` under the *old* `interval_days` recovers the cycle start exactly.

An explicit `next_due_on` in the same request always wins, so a user can pin one occurrence.

> This branch was found by a failing test, not by review: the first implementation guarded on
> `if interval.last_done_on`, so changing 15 → 20 days on a fresh interval silently did nothing.

### 8.5 Completing an action

`complete_interval(...)` with `CompleteRequest{completed_on?, note?}`:

1. `completed_on` defaults to `today()`.
2. Future date → `400 modules.plants.future_date`. More than `MAX_BACKDATE_DAYS` (365) ago →
   `400 modules.plants.date_too_old` (catches a mistyped year while still allowing "I forgot to log last
   month's repotting").
3. Insert `care_log` with `due_on = interval.next_due_on`, `days_late = completed_on - due_on`,
   `action_name` snapshotted.
4. `last_done_on = completed_on`; **`next_due_on = completed_on + interval_days`** (§3.1).
5. `publish_after_commit(CareCompleted(...))`.

Returns both the log row and the updated interval, so a client can show the recomputed next date
without a follow-up read.

### 8.6 Due summary

`due_summary(session, user, *, lookahead_days=0)` → `DueSummary`.

Joins `plant × care_interval` where the plant is readable and not deleted, the interval is `active`,
and `next_due_on <= today + lookahead_days`.

Sorted **most overdue first**, then plant name, then action name.

`summary` is a prose sentence generated by `summarize(count, overdue_count, max_days_overdue)`:

| Condition | Text |
|---|---|
| `count == 0` | `Nothing due today` |
| overdue present | `3 actions due, up to 2 days behind` |
| otherwise | `2 actions due today` |

Note `overdue_count` counts strictly `days_overdue > 0`. An action due *today* is due but not
*behind*.

Generating this server-side means the dashboard tile, the plants screen and the push notification
all state lateness identically.

---

## 9. Calendar projection

`month_calendar(session, user, *, month)` where `month` is `YYYY-MM`. Malformed → `400
modules.plants.invalid_month`.

Returns a flat `CalendarEntry[]` — the client groups by day. Four kinds:

| Kind | Source | Meaning |
|---|---|---|
| `done` | `care_log` row in range | Fact. This happened. |
| `overdue` | `next_due_on < today` | Should have happened, has not |
| `due` | `next_due_on >= today` | The real next occurrence |
| `projected` | arithmetic repeat | Forecast only |

### 9.1 Why `projected` is a distinct kind

Only the first occurrence (`next_due_on`) is real. Every later one is `next_due_on + n ×
interval_days`, which holds **only if every intervening action is done exactly on time** — and §3.1
guarantees it will not be, because completion re-anchors the cycle. Projections MUST therefore be
visually distinct and labelled as estimates, never presented as commitments.

### 9.2 The projection algorithm

Per active interval, for a requested window `[start, end]`:

```
anchor = interval.next_due_on
if start <= anchor <= end:
    emit(anchor, "overdue" if anchor < today else "due")

lower = max(start, today)              # never project into the past
if lower > end: stop
repeat = max(1, ceil((lower - anchor) / interval_days))
while (day := anchor + repeat * interval_days) <= end:
    if day >= lower: emit(day, "projected")
    repeat += 1
```

Two properties this is designed for:

- **No projections into the past.** A projected repeat dated before today never happened — if it
  had, there would be a `care_log` row. Emitting it would be noise contradicting the history shown
  alongside it. Hence a **past month contains `done` entries only.**
- **Bounded regardless of staleness.** `repeat` is computed by ceil-division to jump straight to the
  first occurrence on or after `lower`, rather than stepping from `anchor`. A 1-day interval last
  due in 2020 would otherwise iterate ~2,000 times; it now iterates at most once per day in the
  window. `MAX_CALENDAR_ENTRIES` (2000) is a final backstop.

---

## 10. HTTP API

Base prefix `/api/plants`, tag `plants`. Every route depends on `current_user`.

| Method | Path | Operation id | Description |
|---|---|---|---|
| `GET` | `` | `plants_list` | Paginated list with due rollups |
| `POST` | `` | `plants_create` | Create (201 + `Location`) |
| `GET` | `/due` | `plants_due` | Everything due, across all plants |
| `GET` | `/calendar` | `plants_calendar` | One month of done + scheduled |
| `GET` | `/{plant_id}` | `plants_get` | Plant with its intervals |
| `PATCH` | `/{plant_id}` | `plants_update` | Partial update |
| `DELETE` | `/{plant_id}` | `plants_delete` | Soft delete (204) |
| `GET` | `/{plant_id}/image` | `plants_get_image` | Stream the photo |
| `PUT` | `/{plant_id}/image` | `plants_set_image` | Upload/replace (multipart) |
| `DELETE` | `/{plant_id}/image` | `plants_delete_image` | Remove photo (204) |
| `GET` | `/{plant_id}/history` | `plants_history` | Recent completions |
| `POST` | `/{plant_id}/intervals` | `plants_add_interval` | Add interval (201) |
| `PATCH` | `/{plant_id}/intervals/{interval_id}` | `plants_update_interval` | Update interval |
| `DELETE` | `/{plant_id}/intervals/{interval_id}` | `plants_delete_interval` | Delete interval (204) |
| `POST` | `/{plant_id}/intervals/{interval_id}/complete` | `plants_complete_interval` | Mark done (201) |

### 10.1 Route declaration order (mandatory)

> `/due` and `/calendar` **MUST** be declared **before** `/{plant_id}` in `router.py`.

FastAPI matches in declaration order. With `/{plant_id}` first, `GET /api/plants/due` would try to
parse `"due"` as a UUID and fail with `422`. A code comment marks this; moving those routes is a
regression.

### 10.2 Query parameters

`GET /api/plants` — `limit` (1–100, default 20), `cursor`, `q` (≤200 chars).
`GET /api/plants/due` — `lookahead_days` (0–30, default 0).
`GET /api/plants/calendar` — `month`, **required**, pattern `^\d{4}-\d{2}$`.
`GET /api/plants/{id}/history` — `limit` (1–200, default 50).

### 10.3 Conventions

- Every route declares an explicit `operation_id` of the form `plants_<verb>`; the web client's
  hey-api codegen derives its SDK function names from these.
- Errors are RFC 9457 problem documents (platform §17), codes in §18.
- `plants_complete_interval` returns `201` — it creates a `care_log` row.

---

## 11. Photo storage

### 11.1 Decision: filesystem volume

Photos are files on a mounted volume (`media:/data/media` in `docker-compose.yml`), with only a
relative path in Postgres.

Rationale: `pg_dump` stays small and text-only, and image bytes never pass through the WAL. The cost
is that photos fall outside the database backup, which §20 addresses explicitly.

### 11.2 Layout

Filename is `<plant-uuid>.<ext>`, flat under the media root. **No component of a filename derives
from client input** — the UUID is server-generated and the extension comes from a fixed allow-list —
so there is no traversal surface. `_ensure_inside()` re-checks containment anyway.

### 11.3 Path resolution (a bug worth recording)

`_ensure_inside()` returns a **resolved** path. `_variant_paths()` MUST therefore also return
resolved paths.

> **Regression, fixed.** It originally returned unresolved paths. Because the default media root is
> *relative* (`var/media/plants`), the just-written target (resolved, absolute) never compared equal
> to its own entry in the variant list, so the cleanup loop in `write_image` **deleted the file it
> had just written**. The API returned `has_image: true` and the photo 404'd.
>
> Every unit test passed through this bug, because pytest's `tmp_path` is already absolute and
> resolved. It was caught only by running the real server against the real default config, and is
> now pinned by `test_image_survives_a_relative_media_root`, which explicitly uses a relative root.

### 11.4 Upload

- `PUT /api/plants/{id}/image`, `multipart/form-data`, field `file`. Requires `python-multipart`.
- Empty body → `400 modules.plants.empty_image`. Over the limit → `413 modules.plants.image_too_large`.
- **The declared `Content-Type` is ignored.** The type is sniffed from the leading bytes
  (`sniff_image_type`, checking JPEG/PNG/GIF magic and RIFF-framed WebP). Unrecognised →
  `415 modules.plants.unsupported_image`.
  Rationale: what is stored and later served back is decided by what the bytes actually are, not by
  what the client claimed they were.
- Written to a `.tmp` sibling then `replace()`d — atomic, so a failed write can never leave a
  half-written image being served.
- Previous variants with other extensions are removed, so replacing a PNG with a JPEG leaves exactly
  one file.

### 11.5 Serving

`GET /api/plants/{id}/image` streams via `FileResponse` with the stored content type and
`Cache-Control: private, max-age=300`.

Served through an authenticated route rather than a static mount, so the **same ACL protects the
photo as the plant**. `private` is required: the response is user-specific and MUST NOT enter a
shared cache.

A pointer to a missing file degrades to `404 modules.plants.no_image` rather than erroring.

### 11.6 Known non-atomicity

File writes are not part of the database transaction. A commit failure after a successful write
leaves an orphan file, which is harmless (unreferenced, and overwritten on the next upload since the
path is deterministic per plant). Accepted rather than engineered around, at this scale.

---

## 12. Authorization

- Resource type `plants.plant`. **One ACL row per plant.**
- Intervals and logs have **no ACL rows of their own** — they inherit the owning plant's. Sharing a
  plant shares its whole schedule and history. This is why every interval operation authorizes
  against `plant_id`.
- Create grants `Permission.OWNER` to the creator in the same transaction as the insert.
- `_authorize()` implements the platform's resolve-then-require rule: a caller who cannot **read**
  the plant gets `404`, never `403`. `403 core.acl.forbidden` is reserved for a caller who can see it but
  lacks the specific permission. Existence is not disclosed to someone without read access.
- An interval id that exists but belongs to a different plant → `404 modules.plants.interval_not_found`.
  Interval ids are not addressable outside their plant.

Action → permission mapping is the platform default: `read`/`list` need READ; `create`, `update`,
`delete` and **completing an action** need WRITE.

---

## 13. Dashboard tile

`plants.due`, provided by `tiles.py`, size MEDIUM, `refresh_seconds=300`, `order=20`.

| Field | Value |
|---|---|
| `count` | Total actions due |
| `items` | Up to `TILE_ITEMS_LIMIT` (5), most overdue first |
| `primary` | `"Water — Sansevieria"` |
| `secondary` | `"due today"` / `"1 day behind"` / `"2 days behind"` |
| `href` | `/api/plants/{plant_id}` |
| `empty_text` | `"Nothing due today"` |

The provider is a thin wrapper over `due_summary()` — the tile and the API cannot disagree because
they are the same computation.

Per §3.3 nothing is stored, so the tile is correct the moment an action is completed, subject only
to the client's cache invalidation.

`describe_lateness()` is shared with the notification body (§14) so both phrase lateness identically.

---

## 14. Daily reminder job

`plants.daily_check`, cron `0 7 * * *`, registered via the manifest and implemented in
`reminders.py::notify_due`.

### 14.1 Behaviour

1. One query for all plants with active intervals due within `MAX_LOOKAHEAD_DAYS` (14) — the widest
   any user can configure. A global sweep is correct here: this is a scheduled job, not a request.
2. Group by the plant's **owner** (`plant.user_id`).
3. Per user, read `plants.reminders` settings (§15); skip if `daily_push` is false; narrow to that
   user's own `include_upcoming_days`.
4. If anything remains, send **one digest**:
   - Title — `summarize(...)`, identical wording to the tile: `"2 actions due, up to 2 days behind"`.
   - Body — up to `MAX_BODY_LINES` (10) lines `• Water — Sansevieria (2 days behind)`, then
     `…and N more`.
   - `url` — `{base_url}/plants`.

Silent when nothing is due. A user with a corrupt settings row falls back to defaults with a
warning rather than aborting the whole sweep.

### 14.2 Delivery

`platform.notifier.send(...)` → Procrastinate queues `core.deliver_notification` → Apprise pushes →
a row is written to `core.notification_log` **regardless of outcome**, including
`status='no_channels'` when the user has configured none.

Consequence worth knowing: notifications are durably recorded even with Apprise entirely
unconfigured.

### 14.3 Why there is no in-app inbox

DISP has no notification inbox and this module does not add one. The durable record in
`core.notification_log` is delivery history; the *live* "what do I owe" state is the derived tile.

Rationale: a stored notification per overdue day would accumulate one row per day per action, and
marking the action done would not retract the stale ones — the exact staleness §3.3 exists to
prevent. The two mechanisms are deliberately split: **`core` owns delivery and history, `plants`
owns live state.**

Adding an inbox would be a `core` change (a read route and read/dismiss columns), not a module one.

---

## 15. Settings panel

`plants.reminders`, scope `user`, schema `PlantsSettingsSchema`:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `daily_push` | bool | `true` | Send the morning digest |
| `include_upcoming_days` | int 0–14 | `0` | Also mention actions due within N days |

Stored by the platform settings store as `reminders.daily_push` and
`reminders.include_upcoming_days` under `module_domain='plants'`. Serialized to JSON Schema in the
dashboard manifest, so the client renders the form with no plants-specific code.

**Why the cadence is not configurable.** A `ScheduledJobSpec`'s cron is bound once at wire time and
is process-global; it cannot vary per user. The job therefore runs for everyone at 07:00 server-local
and applies each user's preference internally. Making the *hour* per-user would require either a
finer-grained job or a scheduler feature that does not exist.

---

## 16. Events

```python
@dataclass(frozen=True, slots=True)
class PlantCreated:   plant_id: UUID; user_id: UUID; name: str

@dataclass(frozen=True, slots=True)
class PlantDeleted:   plant_id: UUID; user_id: UUID

@dataclass(frozen=True, slots=True)
class CareCompleted:  plant_id: UUID; interval_id: UUID; user_id: UUID
                      action_name: str; completed_on: date; days_late: int
```

All published with `publish_after_commit` — subscribers never observe a rolled-back transaction.
The module subscribes to `CareCompleted` for structured logging only.

---

## 17. Web client

### 17.1 Screens

| Route | File | Purpose |
|---|---|---|
| `/plants` | `routes/-plants.tsx` | List, due banner, search, create dialog |
| `/plants/$plantId` | `routes/-plant-detail.tsx` | Photo, editable notes, schedule, history, delete |
| `/plants/calendar?month=` | `routes/-plant-calendar.tsx` | Month grid |

Route files export only `Route` and delegate to a `-`-prefixed page component — the repo convention
that keeps per-route lazy chunking working. Nav is registered by one line in
`components/layout/navItems.ts`.

### 17.2 Query keys and invalidation

All keys start with `plants`, so `actionDomainQueryKey('/api/plants/…')` → `['plants']`
prefix-matches every one.

A completion invalidates the **whole `plants` prefix plus the `plants.due` tile**. This is
intentional rather than lazy: completing one action moves that interval's next occurrence, which
changes the list rollups, the detail, the history, the due summary and every cached calendar month.
There is no finer set worth targeting.

Mutations are **not** optimistic. The server decides the next due date (§3.1), and guessing it
client-side would flash a wrong date whenever a completion is back-dated.

### 17.3 Calendar rendering

`lib/calendar.ts` builds a 6×7 Monday-first grid using **UTC-safe arithmetic** (`Date.UTC`,
`timeZone: 'UTC'` on every formatter).

Rationale: calendar days are whole days, not instants. Building them from local-time `Date`s makes
the 1st of the month land on the previous day for anyone west of UTC, shifting the entire grid.
`todayDay()` deliberately reads local Y/M/D and *then* normalizes, so "today" is the day the viewer
would call today.

No date library and no calendar library was added — a month grid is a small amount of arithmetic,
and `Intl` covers the formatting.

### 17.4 Photos cannot be `<img src>`-linked, and currently are — so they do not render

> **Known bug.** This section documented a working solution that was subsequently deleted. It now
> documents the defect instead. The fix is `milestones/server/M18-files.md` (signed URLs); do not
> re-solve it here.

`GET /{plant_id}/image` sits behind the same bearer-only `current_user` dependency as every other
route (§12), and the platform has no cookie-session fallback — `core/auth/dependencies.py:156-167`
reads the `Authorization` header and nothing else, and the refresh cookie is `Path=/api/auth` so it
is never sent here anyway. A plain `<img src="/api/plants/{id}/image">` can therefore never
authenticate: a browser attaches cookies and address-bar navigation to an image load, never a
JS-held bearer token.

**The shipped client does exactly that.** `components/plants/PlantThumbnail.tsx:38` renders
`<img src={imageUrl}>` straight from `plant.image_url`, so every photo 401s. The failure is silent:
`PlantThumbnail`'s `onError` handler (`:42`) falls back to the `Sprout` placeholder that
`milestones/client/M14` §5 added for the database-only-restore case (see the component's own
docstring), and a 401 is indistinguishable from "this plant has no photo".
The unit tests (`tests/unit/plants/PlantThumbnail.test.tsx`) assert the `<img>` element renders, never
that it loads, which is why this survived.

An earlier client solved it with a `usePlantImageUrl` hook that fetched bytes through the
authenticated SDK client and exposed them via `URL.createObjectURL`. That hook was removed in
`33d2b0f` and the plants client rebuilt without it in `1f64607`. The approach is recorded here only
because `M18` cited it as existing code for some time after it stopped existing.

The real fix is a URL a browser can load unauthenticated and the server can still verify: a signed
URL, minted after the module's own `_authorize` check. That is `M18` §9, and it deletes this whole
problem for every module at once rather than reintroducing a per-module blob workaround.

---

## 18. Error code registry

| Code | Status | Raised when |
|---|---|---|
| `modules.plants.not_found` | 404 | Plant absent, soft-deleted, or not readable by the caller |
| `modules.plants.interval_not_found` | 404 | Interval absent, or belongs to a different plant |
| `modules.plants.no_image` | 404 | Plant has no photo, or the file is missing on disk |
| `modules.plants.future_date` | 400 | `last_done_on` / `completed_on` in the future |
| `modules.plants.date_too_old` | 400 | `completed_on` more than 365 days ago |
| `modules.plants.invalid_month` | 400 | `month` not parseable as `YYYY-MM` |
| `modules.plants.empty_image` | 400 | Upload contained no bytes |
| `modules.plants.image_too_large` | 413 | Over `DISP_PLANTS_MAX_IMAGE_BYTES` |
| `modules.plants.unsupported_image` | 415 | Bytes are not JPEG/PNG/WebP/GIF |
| `core.acl.forbidden` | 403 | Caller can read the plant but lacks the permission |
| `core.pagination.invalid_cursor` | 400 | Undecodable cursor (platform-shared) |

---

## 19. Testing

`tests/modules/test_plants.py` — 38 tests, service-layer, against real Postgres.

### 19.1 Coverage

Scheduling (the §3 invariants, including the exact 1st → 3rd → 18th case and the day-2/day-3
"behind" progression), interval CRUD and cadence re-derivation, due summary and sorting, ACL
isolation and read-share, calendar projection (including a past month projecting nothing and a
1-day interval staying bounded), the tile, the reminder job with settings honoured, and the full
photo path.

### 19.2 Fixing the date

An autouse fixture stubs `service.today()`. Because §3.4 makes that the single definition of the
current date, one stub fixes it for `service`, `tiles` and `reminders` alike. Tests needing to
advance time re-stub inside the test.

### 19.3 Client tests

`clients/web/tests/unit/plants/` — 61 tests across calendar arithmetic, due-text wording,
components, and the three page components. Coverage gates: ≥80% lines overall (repo-wide).

### 19.4 A test-design lesson recorded

The §11.3 bug proves that a fixture chosen for convenience can silently satisfy the exact condition
under test. `tmp_path` is absolute; the production default is relative; the bug lived exclusively in
that gap. **Where behaviour depends on a config shape, at least one test MUST use the shipped
default's shape.**

---

## 20. Operational requirements

### 20.1 Photos are not in the database backup

> `scripts/backup.sh` covers Postgres only. **Restoring only the database returns every plant,
> schedule and log with its photo pointer intact and the image gone.**

The failure is graceful (`404 modules.plants.no_image`), not an error, which makes it easy to miss. The
`media` volume MUST be backed up alongside the dump; `docs/operations.md` carries a worked cron
example.

### 20.2 Deployment checklist

- `docker-compose.yml` mounts `media:/data/media` on `api` and sets
  `DISP_PLANTS_MEDIA_ROOT=/data/media/plants`. The **worker does not need the volume** — the
  daily job never touches images.
- Migration: `docker compose run --rm api alembic --name=plants upgrade head`.
- The worker process must be running for reminders to be delivered.

---

## 21. Known limitations and out of scope

| Limitation | Why it is acceptable / what it would take |
|---|---|
| Fixed day intervals only — no "first Sunday", no seasonal cadence | Covers every stated case. A recurrence grammar is a large feature and its interaction with §3.1's completion-anchoring is genuinely unclear — re-anchoring a calendar-aligned rule is ambiguous. |
| No per-interval sharing | ACL is per plant (§12). Finer grain needs a second resource type. |
| Projections assume perfect future adherence | Inherent — §9.1. Mitigated by labelling, not by modelling. |
| One reminder hour for everyone | §15. Needs per-user scheduling the platform does not have. |
| File writes are not transactional | §11.6. Orphans are harmless and self-correcting. |
| `q` searches names only | Descriptions and care notes are not indexed. A GIN index like `notes` uses would be the fix. |
| No Typer CLI commands | Not requested. `notes` shows the pattern if wanted. |

---

## Appendix A — Worked example

The user's original scenario, as verified against a running server.

**Setup.** Create `Sansevieria` (name only). Add `Water` every 15 days, `Green Fertilizer` every 30,
`Fungicide` every 60, `Change soil` every 365. Water was last done 17 days ago, so it came due 2 days
ago; the fertilizer was last done exactly 30 days ago, so it is due today.

**`GET /api/plants/due`:**

```json
{
  "count": 2, "overdue_count": 1, "max_days_overdue": 2,
  "summary": "2 actions due, up to 2 days behind",
  "items": [
    {"action_name": "Water",            "due_on": "2026-07-30", "days_overdue": 2},
    {"action_name": "Green Fertilizer", "due_on": "2026-08-01", "days_overdue": 0}
  ]
}
```

Note `Fungicide` and `Change soil` are absent — not due. `overdue_count` is 1, not 2: the fertilizer
is due *today*, which is not *behind*.

**Complete `Water` today (2026-08-01):**

```
log.due_on        2026-07-30
log.completed_on  2026-08-01
log.days_late     2
interval.next_due_on   2026-08-16     ← completion + 15   (§3.1)
                     ( 2026-08-14     ← what due-date anchoring would give )
```

**`GET /api/plants/due` immediately after** — `"1 action due today"`, containing only
`Green Fertilizer`. Nothing was reconciled; the count simply recomputed (§3.3).

**`GET /api/plants/calendar?month=2026-08`:**

```
done       2026-08-01 Water                 ← fact, from care_log
due        2026-08-01 Green Fertilizer      ← real next occurrence
due        2026-08-16 Water                 ← real next occurrence
projected  2026-08-31 Green Fertilizer      ← forecast
projected  2026-08-31 Water                 ← forecast
```

**Dashboard tile** — `Plant care (1)`, item `Green Fertilizer — Sansevieria` / `due today`.

---

## Appendix B — Files

| File | Contains |
|---|---|
| `__init__.py` | `PlantsModule` — `register()`, `api_router()`, `tile_provider()`, `get_module()` |
| `manifest.py` | `MANIFEST`, `PlantsSettingsSchema` |
| `models.py` | `Plant`, `CareInterval`, `CareLog` |
| `schemas.py` | Pydantic request/response models |
| `service.py` | All business logic — §3 invariants, §8, §9 |
| `router.py` | Thin FastAPI routes (§10) |
| `storage.py` | Filesystem photo I/O, no DB or auth (§11) |
| `config.py` | `PlantsSettings`, allow-list, magic-byte sniffing (§4) |
| `tiles.py` | `plants.due` provider (§13) |
| `reminders.py` | `notify_due` digest sweep (§14) |
| `events.py` | Domain events (§16) |
| `migrations/` | Alembic branch `plants` (§6) |
| `README.md` | Short orientation |
| `TECHNICAL-SPEC.md` | This document |
