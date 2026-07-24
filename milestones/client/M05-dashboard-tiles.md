# M05 — Dashboard and generic tile rendering

**Status:** Not started

**Scope:** `clients/web/src/routes/_app.index.tsx`,
`clients/web/src/components/tiles/{TileGrid,TileCard,TileItemRow,TileActionButton,
TileActionDialog,TileSkeleton,TileError}.tsx`, `clients/web/src/hooks/useIntervalRefresh.ts`.

Covers TECHNICAL-SPEC-WEB.md §13 (Dashboard and generic tile rendering) in full — the spec's own
flagged "requirement most likely to be implemented wrongly."

---

## The one rule everything else in this milestone serves

**No component in `src/components/tiles/` may contain a conditional on a specific tile key or
module domain.** Every rule below exists to make that possible without the UI degrading to
generic mush. Test case 27 (a source-scan test asserting no known module-domain string literal
appears in this directory) is written in *this* milestone, not deferred to M11 — it's the fastest
way to catch a regression the moment someone reaches for `if (tile.key === 'notes.latest')` under
deadline pressure.

## §13.1 Data flow

1. `GET /api/dashboard/manifest` (`qk.dashboard.manifest()`) → `TileSpec[]` across all modules
   (`key`, `title`, `size`, `refresh_seconds`, `order`). Also feeds M04's nav.
2. `GET /api/dashboard/tiles` (`qk.dashboard.tiles()`) → `TileData[]`, one per tile, on first render.
3. Thereafter each tile refreshes independently via `GET /api/dashboard/tiles/{key}`
   (`qk.dashboard.tile(key)`, §13.4).

The manifest determines *which tiles exist and how they're laid out*; the tile endpoints determine
*what they contain*. Never assume a tile exists — a module can be enabled/disabled server-side.

## §13.2 Grid layout

| Breakpoint | Columns | `small` | `medium` | `large` |
|---|---|---|---|---|
| base | 1 | 1 col | 1 col | 1 col |
| md | 2 | 1 col | 1 col | 2 cols |
| lg | 3 | 1 col | 1 col | 2 cols |
| xl | 3 | 1 col | 1 col | 2 cols |

CSS Grid, `grid-auto-rows: min-content`, `align-items: start` (tiles don't stretch to their tallest
neighbor). Order: `TileSpec.order` ascending, then `key` ascending — a stable, server-controlled
sort; the client never re-sorts by anything else. **An unknown `size` value falls back to
`medium`**, not a crash or a layout break — a future module may ship a size this client predates
(test case 16).

## §13.3 `TileCard` anatomy

```
┌─────────────────────────────────────┐
│ Title                    [count]  ⋯ │   header
├─────────────────────────────────────┤
│ • primary text          secondary   │   items (max 5 rendered)
│   timestamp                         │
│ • …                                 │
├─────────────────────────────────────┤
│ [Action]  [Action]                  │   footer, only if actions exist
└─────────────────────────────────────┘
```

- `count` renders as a badge only when non-null; `count: 0` renders `"0"`, not nothing (test 17).
- At most 5 `items` render regardless of how many arrive; excess → muted `"+N more"` line
  (test 19). The server is expected to send few, but the client must not assume it.
- Empty `items` → `empty_text` in muted italic; actions still render (test 18).
- `generated_at` renders as a relative timestamp ("updated 2 min ago") in the header, on
  hover/focus only (a `title` attribute + visually-hidden text) — not permanent visual noise.
- The whole card is **not** a link; only `TileItem.href` values are links.

## §13.4 Per-tile refresh

Each tile mounts its own `useQuery(qk.dashboard.tile(key), ...)` with
`refetchInterval: refresh_seconds * 1000` and matching `staleTime`, seeded via `initialData` from
the bulk `/tiles` response so there's no loading flash for tiles already in that payload.

Refresh pauses when the document is hidden (`refetchIntervalInBackground: false`) and resumes on
visibility — immediately refetching any tile whose interval elapsed while hidden, not waiting for
the next tick.

## §13.5 `TileItem` rendering

| Field | Rendering |
|---|---|
| `primary` | Single line, `text-overflow: ellipsis` |
| `secondary` | Muted; inline on `md`+, own line below on mobile |
| `timestamp` | Relative ("2h ago"), absolute in `title`, wrapped in `<time datetime>` |
| `done` | When non-null, a **read-only** checkbox — see limitation below |
| `href` | Router link (translated per §13.7) when it starts with `/api/`; else plain text |

**Known limitation, by design — not a bug to "fix":** `TileAction` is tile-level with a fixed
`path`; there's no per-item action binding in the current backend contract. `done` is therefore
**display-only**: render it `disabled` with `aria-readonly="true"` (test 25 — clicking it changes
nothing), and do not invent a URL-template convention to make it interactive. Making it real
requires a backbone contract amendment (per-item actions on `TileItem`) that is explicitly out of
this version's scope — do not build a workaround.

## §13.6 Tile actions

`TileAction`: `id`, `label`, `method`, `path`, optional `body_schema`.

- **No `body_schema`**: click fires the request immediately. `method: "DELETE"` requires a
  confirmation dialog first (test 20).
- **With `body_schema`**: click opens `TileActionDialog` containing a `SchemaForm` (M06 — this
  milestone depends on M06's `SchemaForm` component existing; build in whichever order is
  convenient but wire the actual dependency, don't stub it permanently) generated from that schema
  (test 21). Submit issues the request with the form value as the JSON body.
- On success: invalidate `qk.dashboard.tile(key)` **and** any query key whose first segment matches
  the action path's module domain, derived generically from the path (e.g. an action on
  `/api/notes` invalidates `qk.notes.all()`) — this is a path-derived rule, not a per-module special
  case (test 22).
- Errors follow M02's §7.3 table; a failing action keeps the dialog open with the error inline so
  input isn't lost (test 23).

## §13.7 `href` translation

`TileItem.href` values are API paths (`/api/notes/{id}`). One generic rule: strip the `/api` prefix
and look the result up in M04's `MODULE_ROUTES` map. `/api/notes/abc` → `/notes/abc`. An unmapped
path renders as plain text, not a broken link (test 26).

## §13.8 Tile failure and loading

- Loading: `TileSkeleton` — correctly-sized card, three muted bars, no shimmer.
- The server already substitutes a fallback tile for a failed provider
  (`_fallback_tile` in `src/disp/core/dashboard.py:61-70`, confirmed in the current backend) — it
  arrives as valid `TileData` with `empty_text: "This tile failed to load"`. Render it like any
  other tile; **do not** special-case that string.
- If the *request itself* fails (network, 5xx): render `TileError` — title, muted error line, Retry
  button that refetches only that tile.
- Each tile wrapped in its own error boundary — one failing tile must never affect siblings
  (test 24).

## §13.9 Empty dashboard

No tiles in the manifest → `EmptyState` with Appendix D copy directing to the modules documentation.
A real state on a fresh install with no modules enabled — not a hypothetical edge case.

## Dependencies

- **M02** (generated client, query keys) and **M04** (the `_app` shell this route renders into,
  and the manifest query the nav also consumes — reuse the same `useQuery` call, don't duplicate
  the manifest fetch).
- **M06** for `SchemaForm`, consumed by `TileActionDialog`. If M06 isn't done yet, build
  `TileActionDialog` against `SchemaForm`'s intended props signature and land the integration once
  M06 exists — don't invent a parallel schema-form implementation here.

## Open questions / judgment calls for the implementer

- §13.2's table gives per-size column spans but not exact `grid-template-columns` values — use
  `repeat(auto-fill, minmax(...))` or explicit spans per size; either satisfies the table as long as
  the rendered column counts match at each breakpoint. Verify against the table directly, not by
  eyeballing.
- The acceptance criteria (§25 #11) requires a mocked manifest containing an *unknown* module domain
  to render correctly, including an action dialog from an unfamiliar `body_schema`. Build this as an
  explicit test fixture now (a manifest/tile pair with a domain that doesn't exist anywhere else in
  the codebase) rather than relying on `notes` alone to prove genericness — `notes` being correct
  doesn't prove the *next* module will be.

## Verification

- Test cases 15–27 (§23.3) — write these as component tests now, in this milestone, given how easy
  a key/domain conditional is to reintroduce later without noticing.
- Manual: with the dev backend's `notes.latest` tile as the only real tile, confirm layout, refresh,
  and the quick-add action dialog all work; then swap in the unknown-domain fixture above via MSW
  and confirm identical behavior with zero code changes.
