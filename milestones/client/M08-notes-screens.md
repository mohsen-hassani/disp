# M08 — Notes screens

**Status:** Not started

**Scope:** `clients/web/src/routes/{_app.notes.index.tsx,_app.notes.$noteId.tsx}`,
`clients/web/src/components/notes/{NoteList,NoteCard,NoteEditor,ShareDialog}.tsx`.

Covers TECHNICAL-SPEC-WEB.md §16 (Notes screens) in full.

---

## Why `notes` gets bespoke screens at all

Every other module in this backend expresses itself only through dashboard tiles and settings
panels (M05/M06's generic renderers). `notes` is the demonstration that a module can ship a full
bespoke screen when a tile isn't enough — mirroring exactly how `milestones/M13-notes-module.md`
frames the backend's `notes` module as "the demo module... its implementation quality is held to
the same standard as the backbone." Everything here uses only the generated client from M02 — no
hand-written request shapes, even though these are bespoke screens.

## §16.1 `/notes` — list

- **Toolbar**: search input (debounced 300ms, bound to `q`), pinned-only filter toggle, "New note"
  button.
- **List**: `useInfiniteQuery` on `qk.notes.list({q, pinned})`. Server ordering is
  `pinned DESC, created_at DESC` (backend `src/disp/modules/notes/router.py` / confirmed in
  `milestones/M13-notes-module.md` §18.3) — **the client MUST NOT re-sort**, even though a naive
  client-side sort-by-title might look like a nice-to-have; the server's order is the contract.
- **`NoteCard`**: pin indicator, title (or first line of body when title is null), two-line body
  preview, relative created time, overflow menu (Open, Pin/Unpin, Share, Delete).
  - Row click → `/notes/:id`.
  - Pin toggle is **optimistic** (one of the three permitted exceptions in §10.4 — snapshot via
    `onMutate`, rollback via `onError`, invalidate via `onSettled`).
  - Delete asks for confirmation, then removes the row **optimistically** (also one of the three
    exceptions).
  - Search term reflected in the URL (`?q=`) — a search is linkable and survives reload.
- **States**: loading (3 skeleton rows), empty-no-filters (EmptyState, "Create your first note" CTA),
  empty-with-filters ("No notes match" + Clear filters button), error (retry).

**No `total` count is available** (backend amendment A3 was declared out of scope in
[[M00-backbone-amendments]] — cursor pagination doesn't support it, and the spec's own §3 text
forbids adding it unilaterally). Build the list to work correctly with only `items`/`next_cursor`/
`has_more` — no "showing X of Y" affordance anywhere in this screen.

## §16.2 `/notes/:noteId` — detail

- Header: title (or "Untitled"), pin toggle, overflow menu (Share, Delete), Back.
- Body: **plain text with preserved whitespace** (`white-space: pre-wrap`). **Markdown is not
  rendered.** The backend's `body` field is plain text (confirmed:
  `milestones/M13-notes-module.md` §18.2/§18.3 has no markdown processing anywhere in the notes
  module); rendering it as Markdown would misrepresent stored data and add an XSS surface that
  doesn't exist today. Do not add a Markdown renderer under any future "nice to have" framing —
  this is an explicit backend-and-frontend joint invariant, not just a client stylistic choice
  (test case 39 asserts a body containing literal `<script>` and Markdown syntax renders as inert
  text).
- Metadata: created/updated timestamps, absolute, locale-formatted via `Intl` (never `moment`/
  `date-fns` — forbidden per M01's stack table).
- Inline edit: clicking the body or the Edit button switches to a textarea with Save/Cancel.
  `Cmd/Ctrl+Enter` saves, `Escape` cancels with an unsaved-changes confirmation.
- `404 notes.not_found` → the not-found screen, not a toast (test case 40) — the backend's 404-vs-403
  distinction (`milestones/M13-notes-module.md`'s "Design notes" section: existence hidden on
  no-read-access, `403 acl.forbidden` on read-but-not-write) means a 404 here specifically means
  "this note doesn't exist or you can't see it," which deserves a full screen state, not a
  passing toast that leaves the stale detail view visible underneath.

## §16.3 Note creation

A dialog reachable from: the list toolbar's "New note" button, the dashboard tile's quick-add
action (M05's `notes.latest` tile, which already defines a `body_schema` for exactly this — but
note that the *dialog itself* here is the bespoke one from this milestone, distinct from M05's
generic `TileActionDialog`; the tile's quick-add and this screen's create dialog may end up sharing
the underlying create mutation but are two different UI entry points per the spec's own tree
listing both), and a keyboard shortcut (`n`, §16.5).

Fields: title (optional), body (required, autofocused, ≤20000 chars with a counter appearing past
19000), pin switch. `Cmd/Ctrl+Enter` submits.

Success: close dialog, toast with an "Open" action linking to the new note, invalidate per the
table below.

## §16.4 Sharing

`ShareDialog`: email input, read/write radio group, `POST /api/notes/{id}/share`.

- `404 notes.user_not_found` → email field error, "No user with that email. They need an account
  first."
- `400 notes.cannot_share_with_self` → email field error.
- `403` → dialog closes with a toast; only owners may share (matches the backend's `owner`-only
  requirement on this route).
- **The backend provides no endpoint listing a note's existing grants** — confirmed, no such route
  exists in `src/disp/modules/notes/router.py`. The dialog MUST NOT display current shares; state
  plainly that sharing is additive (Appendix D copy) and that removing access requires the API. Do
  not invent an endpoint or fake a "who has access" list from client-side guesswork.

## §16.5 Keyboard shortcuts

Global, active only when no input has focus:

| Key | Action |
|---|---|
| `g` then `d` | Go to dashboard |
| `g` then `n` | Go to notes |
| `n` | New note dialog |
| `/` | Focus search (on `/notes`) |
| `?` | Show shortcuts dialog |
| `Escape` | Close topmost overlay |

## Invalidation matrix for this milestone (§10.3, reproduced for the mutations built here)

| Mutation | Invalidates |
|---|---|
| Create note | `qk.notes.list(*)`-shaped keys (all filters), `qk.dashboard.tile('notes.latest')` |
| Update note | list keys, `qk.notes.detail(id)`, the notes tile |
| Delete note | list keys, the notes tile; **removes** `qk.notes.detail(id)` from the cache entirely |
| Share note | `qk.notes.detail(id)` |

## Dependencies

- **M02** (generated client, query keys, error mapping), **M03** (auth guard via M04), **M04**
  (route shell, `MODULE_ROUTES['notes']` entry). Independent of M00/M06 — notes has no settings
  panel in the current manifest (confirmed: `settings_panels=()` in the notes module's manifest per
  `milestones/M13-notes-module.md` §18.1).

## Open questions / judgment calls for the implementer

- The quick-add tile action (M05) and this milestone's creation dialog both ultimately call
  `POST /api/notes` — decide whether they share a single `useCreateNote` mutation hook (recommended,
  avoids the invalidation matrix above being implemented twice and drifting) or remain independent.
- §16.3 doesn't specify what happens to the dialog's `body_schema`-style validation vs. this
  milestone's own `react-hook-form`/Zod validation for the bespoke create dialog — these are two
  different code paths (M05's generic schema-driven quick-add vs. this milestone's hand-built form)
  and should use each one's own native validation approach rather than trying to unify them.

## Verification

- Test cases 35–41 (§23.3): list renders/searches/reflects `q` in URL; pin toggle optimistic +
  rollback; delete optimistic + restore-on-error; create invalidates list + tile; body renders
  `<script>`/Markdown literally as text; `404` on detail renders the not-found screen; share
  `404 notes.user_not_found` maps to the email field.
- Full CRUD + search + pin + share against the real backend (§25 acceptance criterion 14) — this is
  the milestone where that full loop first becomes testable end-to-end, since it's the first to
  exercise every notes route.
