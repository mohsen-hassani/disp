# M14 — `plants` screens (full CRUD)

**Status:** Complete. All five routes, `PlantEditor`, `IntervalList`/`IntervalFormDialog`/
`CompleteDialog`, `PhotoUpload`, and the calendar grid are implemented per this brief; `plants` is
registered in `MODULE_SCREENS`. `tests/unit/plants/` (59 tests) covers the six invariant cases in
§7, including the reschedule-from-completion-date assertion against a mismatched due-date+interval
vs completion-date+interval scenario. `tests/e2e/plants.spec.ts` drives the full create → add
interval → mark done → verify reschedule → delete round trip through the real UI; written and
verified manually against a real `docker-compose.e2e.yml` backend (screenshots confirmed the
Aug 7 completion → Aug 22 next-due reschedule, not the naive Aug 19), but not run headless via
Playwright itself — this sandbox's network blocks the Chromium binary download, so a human with
network access should do that run once before relying on it in CI. `pnpm lint`, `tsc --noEmit`, and
`pnpm test --run --no-file-parallelism` all pass (82.8% overall line coverage, ≥80% gate).

**Scope:** `clients/web/src/routes/_app.plants.*`, `clients/web/src/routes/-plant*.tsx`,
`clients/web/src/components/plants/`, `clients/web/src/api/queryKeys.ts`,
`clients/web/src/api/queries.ts`, `clients/web/src/modules/registry.ts` (one line),
`clients/web/src/lib/icons.ts` (already carries `sprout`).

Depends on **M13** (manifest-driven navigation) and **M17** (the backend contract). Both are
complete: `plants` already declares `client_nav` and a `plants.due` tile nav button, so the nav
entry and the tile's "Manage plants" button appear the instant `MODULE_SCREENS` gains `'plants'` —
**no contract, spec, or shell work is part of this milestone.** If you find yourself editing
`navItems.ts`, `SideNav.tsx`, or anything in `src/components/tiles/`, stop: something is wrong.

Covers WEB-SPEC §1.2 (amended: plants screens are in scope) and goal W5, extended to a second
module.

---

## 1. The domain rule that everything else serves

**Completing a care action reschedules from the completion date, not the due date.** Done on the 3rd
for a 15-day cycle → next due the **18th**, not the 16th. Due/overdue state is **derived at read
time, never stored**.

Consequences for this client, all of them load-bearing:

- **Never compute a next-due date locally.** `POST /api/plants/{id}/intervals/{iid}/complete`
  returns `CompleteResult { log, interval }` where `interval` already carries the recomputed
  `next_due_on` and `days_overdue`. Use it; do not add `interval_days` to anything yourself.
- **Never cache derived staleness across a date boundary.** `days_overdue` is computed against the
  caller's "today". A tab left open overnight holds stale values — treat `days_overdue` as a
  server-rendered fact with a short `staleTime`, not a stable property of the row.
- An optimistic update on "mark done" would have to predict a date only the server can compute.
  **Don't.** Use a plain pending mutation (the §10.4 optimistic exceptions are pin-toggle and
  delete on `notes`, and they do not generalise here).

`src/disp/modules/plants/TECHNICAL-SPEC.md` is the as-built source of truth for every scheduling
invariant. Read it before designing the detail screen.

## 2. Routes

Mirror the `notes` file-based convention exactly.

| Path | Route file | Page component | Title |
|---|---|---|---|
| `/plants` | `_app.plants.index.tsx` | `-plants.tsx` | `Plants · DISP` |
| `/plants/new` | `_app.plants.new.tsx` | `-plant-new.tsx` | `New plant · DISP` |
| `/plants/calendar` | `_app.plants.calendar.tsx` | `-plant-calendar.tsx` | `Plant calendar · DISP` |
| `/plants/:plantId` | `_app.plants.$plantId.tsx` | `-plant-detail.tsx` | `<plant name> · DISP` |
| `/plants/:plantId/edit` | `_app.plants.$plantId.edit.tsx` | `-plant-edit.tsx` | `Edit <plant name> · DISP` |

**The `-` prefix is load-bearing, not a style choice.** Every real route file must export *only*
`Route`; any additional export blocks `@tanstack/router-plugin`'s `autoCodeSplitting` from
producing a per-route lazy chunk. The page component therefore lives in a sibling `-name.tsx` (which
the router ignores), takes plain props, and is directly unit-testable without a test router.

**Declaration order matters on the backend and must be mirrored in intent here:** `/plants/new` and
`/plants/calendar` are static segments that must not be swallowed by `/plants/:plantId`. TanStack
Router ranks static above dynamic automatically, but a `plantId` param validator that accepts
non-UUIDs will produce confusing 404s — validate it as a UUID and let a non-match fall through.

Detail-loader pattern, per `_app.notes.$noteId.tsx`:

```ts
loader: async ({ context, params }) => {
  try { await context.queryClient.ensureQueryData(plantDetailQueryOptions(params.plantId)); }
  catch (error) { if (isProblem(error) && error.status === 404) throw notFound(); throw error; }
}
```

If any `beforeLoad` reads a query a parent `loader` populates, it must `await ensureQueryData`
itself — never bare `getQueryData`. See `CLAUDE.md`'s note on the `/settings/$domain` bug.

## 3. Registration

One line, and it is the entire integration:

```ts
// src/modules/registry.ts
export const MODULE_SCREENS: ReadonlySet<string> = new Set(['notes', 'plants']);
```

**This will immediately fail `tests/unit/tiles/no-domain-literals.test.ts`** if the word `plants`
appears anywhere under `src/components/tiles/` — including in a comment. That is the test doing its
job (M05 case 27): tile components must stay generic. Put plants-specific code in
`src/components/plants/`, never in `tiles/`.

Adding this line also makes `plants.due`'s tile items into real links (`/api/plants/{id}` →
`/plants/{id}`, WEB-SPEC §13.7) and renders the "Manage plants" footer button. Both come for free;
verify them rather than building them.

## 4. API surface

Everything below is already generated in `src/api/generated/sdk.gen.ts` with **zero client
references today** — no hand-written request shapes (goal W7).

| Screen | Calls |
|---|---|
| list | `plantsList` → `PagePlantOut` (`{ items, next_cursor, has_more }` — cursor pagination, use `useInfiniteQuery` as `NoteList` does) |
| create | `plantsCreate` (`PlantCreate`: `name` 1–120, `description` ≤2000, `care_notes` ≤20000) |
| detail | `plantsGet` → `PlantDetailOut` (= `PlantOut` + `intervals: CareIntervalOut[]`), `plantsHistory` → `CareLogOut[]` |
| edit | `plantsUpdate` (`PlantUpdate`, all fields optional — PATCH semantics) |
| delete | `plantsDelete` (soft delete, 204) |
| intervals | `plantsAddInterval` (`name`, `interval_days` 1–3650, optional `last_done_on`), `plantsUpdateInterval` (also `next_due_on`, `active`), `plantsDeleteInterval` |
| complete | `plantsCompleteInterval` (`CompleteRequest`: optional `completed_on`, optional `note` ≤2000) → `CompleteResult` |
| calendar | `plantsCalendar` (`month=YYYY-MM`; 400 on a malformed month) → `CalendarOut` |
| photo | `plantsSetImage` (multipart), `plantsGetImage`, `plantsDeleteImage` |

`PlantOut` already carries the rollups a list view needs — `due_count`, `max_days_overdue`,
`next_due_on`, `has_image`, `image_url` — so **badge rows straight from the list response**; there
is no per-row round trip to make.

## 5. Screens

**List (`/plants`).** Infinite list of cards. Each row: name, a due badge derived from
`due_count`/`max_days_overdue`, next-due date, thumbnail when `has_image`. Toolbar: "Add plant"
(→ `/plants/new`), a link to `/plants/calendar`. Four states, as `NoteList` has them: pending
skeletons / error + Retry / empty / empty-with-filters. Overdue must **not** be signalled by colour
alone (§21 A8) — pair it with text or an icon.

**Create (`/plants/new`) and edit (`/plants/:id/edit`).** One `PlantEditor` component with
`mode: 'create' | 'edit'`, exactly as `NoteEditor.tsx` is built. Care intervals are **not** part of
the create form — create the plant, then add intervals on the detail screen. A create form that
also managed a variable-length interval list would be two forms wearing one coat.

**Detail (`/plants/:id`).** The centre of this milestone:
- header: name, photo, edit/delete actions (delete behind a confirm dialog);
- interval list: each with name, cadence, `next_due_on`, an overdue indicator from `days_overdue`,
  and a **"Mark done"** action opening a small dialog for optional `completed_on` + `note`;
- add/edit/delete interval;
- recent history from `plantsHistory` (`CareLogOut`: `action_name`, `due_on`, `completed_on`,
  `days_late`, `note`).

Back-dating `completed_on` is allowed up to a year and is the point of the field — "I actually
watered it on Saturday" must schedule the next one correctly. Future dates are rejected server-side
(422); surface that inline rather than pre-validating with your own rule that could drift.

**Calendar (`/plants/calendar`).** Month grid from `CalendarOut.entries`. Four `kind` values, each
visually distinct: `done`, `overdue`, `due`, `projected` — **`projected` renders greyed out**,
because completing early or late moves it. Month navigation writes `?month=YYYY-MM` to the URL
(validated in `validateSearch`) so a month is linkable and back/forward works.

**Photo.** The one genuinely new capability: multipart upload via `plantsSetImage`. Accepts
`image/jpeg`, `image/png`, `image/webp`, `image/gif`; max 2 MiB (`max_image_bytes`) — check size
client-side before upload for a fast error, but still handle the server's rejection.

> **Plant photos are files on a volume, not rows** (`DISP_PLANTS_MEDIA_ROOT`). `pg_dump` does not
> contain them, so a database-only restore leaves `has_image: true` with the file gone and
> `plantsGetImage` returning `404 plants.no_image`. **Render that as a graceful placeholder, never a
> broken `<img>`.** This is a real operational state, not a hypothetical.

## 6. Patterns to reuse, not reinvent

- **Forms: `react-hook-form` + `zodResolver`**, as `NoteEditor.tsx` does. `SchemaForm` is only for
  *server-declared* JSON Schema (settings panels, tile action dialogs) — never for bespoke screens.
- **Read queries**: `queryOptions()` / `infiniteQueryOptions()` factories in `src/api/queries.ts`.
- **Query keys**: add a `plants:` block to `src/api/queryKeys.ts` — the single source; no ad-hoc key
  literal is permitted anywhere else in the app. Suggested shape mirroring `notes`:
  `all()`, `list(filters)`, `detail(id)`, `history(id)`, `calendar(month)`.
- **Mutations + invalidation**: follow `useNoteMutations.ts`. Every plants mutation must invalidate
  the list prefix, the affected `detail(id)`, **and `qk.dashboard.tile('plants.due')`** — otherwise
  the dashboard count contradicts the screen the user just acted on. (A tile *action* would
  invalidate `['plants']` automatically via `actionDomainQueryKey`; a screen mutation gets no such
  help and must do it explicitly.)
- **Errors**: `mapValidationErrors` for 422 → `setError`/`setFocus`; a `describePlantError` mapping
  `acl.forbidden` / 404 / 5xx to copy, as `describeNoteError` does.
- **API call shape**: destructure `{ data, error, response }`, check `!response?.ok || !data`,
  throw. Everywhere, without exception.
- **Design**: `docs/design-system/` for tokens and component APIs, translated into this repo's
  Tailwind + Radix conventions — never imported verbatim. Shipped code in
  `clients/web/src/components/` wins any conflict; flag it rather than silently overriding.
- No raw hex or arbitrary Tailwind values (`text-[#3b82f6]`) — semantic tokens only (M04 §11).

## 7. Verification

- `tests/unit/plants/` — one file per screen/component. Coverage gate is ≥80% lines overall
  (`vitest.config.ts`); a number that looks implausibly low is a config problem to find, not a
  target to lower.
- Cases that must exist, because they encode the invariants rather than the markup:
  1. completing an action renders the **server's** returned `next_due_on`, and a test where
     completion-date + interval ≠ due-date + interval proves the client didn't compute it;
  2. back-dated completion sends `completed_on` and reschedules from it;
  3. a 422 on a future `completed_on` surfaces inline without losing form input;
  4. `has_image: true` with a 404 image renders a placeholder, not a broken image;
  5. a `projected` calendar entry is visually distinguished from `due`;
  6. every mutation invalidates `qk.dashboard.tile('plants.due')`.
- `tests/e2e/plants.spec.ts` — create → add interval → mark done → verify the reschedule → delete.
- `pnpm lint`, `tsc --noEmit`, and `pnpm test --run --no-file-parallelism` (the suite has
  pre-existing `userEvent` timeouts under parallel load — see M13's note; don't chase them).
- **Manual**: `plants` appears under **Modules** in the side nav; the `plants.due` tile shows
  "Manage plants" reaching `/plants`; tile items deep-link to `/plants/:id`; the bottom nav now has
  4 items (Dashboard, Notes, Plants, Settings) and still no "More" sheet — a fifth would trip it.

## 8. Explicit non-goals

Do not add per-item tile actions (the `TileItem.done` checkbox stays read-only — WEB-SPEC §13.5's
documented limitation requires a backbone amendment). Do not add offline mutation queuing (§1.2).
Do not add plants push notifications — the daily reminder is a server-side job with a settings panel
already rendered generically at `/settings/plants`.
