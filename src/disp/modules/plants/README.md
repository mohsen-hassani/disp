# plants

Plant care schedules: what needs watering, feeding or repotting, and when.

## Model

Three tables in the `plants` schema:

| Table | Holds |
|---|---|
| `plant` | Name, optional description, free-text `care_notes`, optional photo pointer |
| `care_interval` | One recurring action — "Water", every 15 days — with its `next_due_on` |
| `care_log` | Append-only record of every completed action |

`care_notes` is prose ("bright indirect light, let it dry out between waterings"). The
machine-readable part — what recurs and how often — lives in `care_interval`, one row per action.
A plant can have as many as you like: watering, several different fertilizers, fungicide, repotting.

## The one rule that matters

**Completing an action reschedules from the completion date, not the due date.**

Watering on a 15-day cycle falls due on the 1st. You do it on the 3rd. The next one is due on the
**18th** (3rd + 15), not the 16th (1st + 15). Anchoring to the due date instead would make anyone
who runs late permanently late, and the drift would compound with every cycle.

`last_done_on` stays `NULL` until the action has genuinely been completed once — "never done" and
"done today" are different facts, and the calendar must not invent history. Where a cycle start is
needed before that (re-deriving `next_due_on` when the cadence changes), it is worked backwards
from `next_due_on` under the previous cadence.

## Due state is derived, never stored

There is no "notification" or "reminder" row. Whether something is due, and how far behind it is,
is computed at read time as `today - next_due_on`:

- `< 0` — not due yet
- `0` — due today
- `> 0` — this many days behind

So the dashboard tile is correct the instant an action is marked done, and can never go stale or
need reconciling. `today` is the date in `DISP_TIMEZONE`, not the server's UTC date — every
comparison goes through `service.today()`.

## Surfaces

- **Tile `plants.due`** — count plus the five most overdue actions. Derived per request.
- **Scheduled job `plants.daily_check`** (07:00 daily) — one digest per user via
  `platform.notifier.send(...)`, which queues through Procrastinate, pushes through Apprise, and
  leaves a durable row in `core.notification_log`. The tile is the live state; this is the nudge.
- **Settings panel `plants.reminders`** — per-user `daily_push` toggle and an optional look-ahead
  window. The cron is fixed at manifest wire time, so the job runs for everyone and applies each
  user's preference internally.
- **`GET /api/plants/calendar?month=YYYY-MM`** — past days come from `care_log` (fact); today
  onward comes from `next_due_on` plus arithmetic repeats, tagged `projected` because completing
  early or late shifts every later occurrence. A past month therefore shows history only.

## Photos

Stored on a filesystem volume (`DISP_PLANTS_MEDIA_ROOT`, mounted at `/data/media/plants` in
`docker-compose.yml`), not in Postgres — `pg_dump` stays small and text-only, but **the volume
needs backing up separately**. Filenames are `<plant-uuid>.<ext>`, derived entirely from the UUID
and a sniffed content type; no part comes from client input.

The declared `Content-Type` is ignored — the type is sniffed from the leading bytes and rejected
unless it is JPEG, PNG, WebP or GIF. Serving goes through `GET /api/plants/{id}/image` rather than
a static mount so the same ACL applies to the photo as to the plant.

## Access control

One ACL row per plant (`plants.plant`). Intervals and logs have none of their own — they inherit
the owning plant's, so sharing a plant shares its whole schedule. A caller who cannot read a plant
gets 404, never 403; 403 is reserved for a caller who can see it but lacks the permission.
