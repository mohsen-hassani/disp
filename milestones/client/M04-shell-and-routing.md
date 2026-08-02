# M04 — Routing, design system, and application shell

**Status:** Not started

**Scope:** `clients/web/src/{main.tsx,routeTree.gen.ts}`,
`clients/web/src/routes/{__root.tsx,_app.tsx,_app.index.tsx,$404.tsx}`,
`clients/web/src/components/layout/{AppShell,SideNav,BottomNav,TopBar}.tsx`,
`clients/web/src/hooks/{useMediaQuery.ts,useOnlineStatus.ts}`, `clients/web/src/lib/theme.ts`
(runtime theme switching — the CSS tokens were M01's job).

Covers TECHNICAL-SPEC-WEB.md §9 (Routing), §11 (Design system), §12 (Application shell and
navigation).

---

## §9. Routing

TanStack Router, file-based routes, typed params. Route table (full — `_app.notes.*` and
`_app.settings.*` etc. are stub components wired here and filled in by their own milestones):

| Path | Component | Guard | Document title |
|---|---|---|---|
| `/login` | Login (M03) | anonymous-only (redirect to `/` if authenticated) | `Sign in · DISP` |
| `/accept-invite` | AcceptInvite (M03) | none | `Accept invitation · DISP` |
| `/` | Dashboard (M05) | auth | `Dashboard · DISP` |
| `/notes` | NotesList (M08) | auth | `Notes · DISP` |
| `/notes/:noteId` | NoteDetail (M08) | auth | `<note title> · DISP` |
| `/settings` | SettingsIndex (M06) | auth | `Settings · DISP` |
| `/settings/account` | Account (M07) | auth | `Account · DISP` |
| `/settings/tokens` | Tokens (M07) | auth | `API tokens · DISP` |
| `/settings/:domain` | ModuleSettings (M06) | auth | `<panel title> · DISP` |
| `/admin/invites` | Invites (M07) | auth + `is_admin` | `Invitations · DISP` |
| `*` | NotFound | none | `Not found · DISP` |

Rules:

- The `_app` guard MUST await M03's auth bootstrap. While `loading`, render the shell skeleton —
  never flash the login screen. This is the concrete wiring point for M03's bootstrap sequence.
- Unauthenticated access to a guarded route → `/login?next=<pathname+search>`.
- A non-admin reaching `/admin/*` renders a 403 screen; it must **not** redirect — the URL stays
  honest about what's there and why it's blocked.
- `/settings/:domain` validates `domain` against the manifest's settings panels (M06 owns the
  manifest query) and renders the 404 screen for an unknown domain **without a network call** — the
  manifest is already in the query cache by the time this route can be reached.
- Route-level code splitting is mandatory: every route is a lazy chunk (`React.lazy` / the router's
  own lazy-route mechanism).
- Scroll position resets to top on navigation except back/forward, where it restores.
- `document.title` is set per-route from the table above.

## §11. Design system

Tokens and light/dark values were defined in M01's `src/styles/index.css` (Appendix C, verbatim).
This milestone owns the *runtime* behavior:

- **Theme switching** (`src/lib/theme.ts`): resolves `light`/`dark`/`system`, applies
  `data-theme` to `<html>`, persists the choice to `disp.theme`, and updates `<meta name="theme-color">`
  to match the resolved theme. The user menu's Theme submenu (§12.4, below) is this milestone's UI for it.
- **Typography**: system font stack only, no web fonts. Scale (rem): `0.75, 0.875, 1, 1.125, 1.25,
  1.5, 2`. Body `1rem` mobile / `0.9375rem` desktop. Line height 1.5 body / 1.25 headings. Max prose
  measure `68ch` (used by M08's note body).
- **Spacing/radius/elevation**: Tailwind's 4px base scale; layout gaps `4,8,12,16,24,32,48`.
  Radius `--radius-sm:6px` (controls), `--radius-md:10px` (cards), `--radius-lg:16px` (dialogs).
  Elevation via borders/background steps except overlays, which use `--shadow-overlay`.
- **Breakpoints**: `base`(0, 1-col bottom nav) / `sm`(640px, wider gutters) /
  `md`(768px, 2-col tiles + side nav appears) / `lg`(1024px, 3-col tiles) /
  `xl`(1280px, 3-col, max-width 1200px centered). Mobile-first throughout.
- **Motion**: 120ms state changes, 200ms overlays, `cubic-bezier(0.2,0,0,1)`. Every transition
  wrapped so `prefers-reduced-motion: reduce` collapses it to `0ms`. No shimmer, no parallax,
  no scroll-linked animation.

Raw hex values and arbitrary Tailwind values (`text-[#3b82f6]`) are forbidden anywhere in components
built from this milestone onward — always reference the semantic tokens.

## §12. Application shell and navigation

### Structure

```
┌──────────────────────────────────────────┐
│ TopBar: logo · page title · user menu    │  ← md+: global search slot (unused v1)
├────────┬─────────────────────────────────┤
│ SideNav│  <Outlet />                     │  ← md+ only
│ (md+)  │                                 │
└────────┴─────────────────────────────────┘
┌──────────────────────────────────────────┐
│ BottomNav (base–sm only)                 │
└──────────────────────────────────────────┘
```

### Navigation items

Built from the dashboard manifest query (`qk.dashboard.manifest()`, M05 owns the actual query hook,
this milestone consumes it) plus fixed entries:

| Order | Label | Icon | Path | Visibility |
|---|---|---|---|---|
| 1 | Dashboard | `layout-dashboard` | `/` | always |
| 2 | Notes | `sticky-note` | `/notes` | when `notes` is in the manifest |
| 3 | Settings | `settings` | `/settings` | always |
| 4 | Invitations | `user-plus` | `/admin/invites` | `is_admin` only, desktop side nav only |

**`MODULE_ROUTES` constant** (§12.2): a single, clearly commented map — v1 has exactly one entry,
`notes`. A module registering tiles with no bespoke screen appears only on the dashboard; only
modules with a `MODULE_ROUTES` entry get a nav item. This is deliberate, not an oversight — bespoke
screens require bespoke code and the client must not pretend a module has a screen it doesn't. Adding
a future module's screen should be a one-line addition to this map plus the screen itself; keep it
that simple.

### Mobile bottom nav

Fixed to bottom, `env(safe-area-inset-bottom)` padding. Max 4 items — a 5th collapses into a "More"
sheet. Targets ≥56px tall, ≥64px wide. Active item indicated by icon fill + label color, never color
alone (§21 A8).

### User menu

Radix dropdown in TopBar: display name + email (truncated), then Account, API tokens, Theme submenu
(Light/Dark/System), Sign out. Sign out uses the explicit-logout path from M03 (§8.6).

### Safe areas and viewport

`index.html`'s viewport meta was set in M01. This milestone's shell components pad with
`env(safe-area-inset-*)` on all four sides wherever content would otherwise sit under system UI
(notch, home indicator, gesture bar).

## Dependencies

- **M03** — the `_app` guard is the concrete consumer of `AuthProvider`'s bootstrap/`useAuth()`.
- **M02** — query client setup (§10.1 defaults) is wired into `main.tsx` here, even though the
  per-query configuration (§10.2) and invalidation matrix (§10.3) are applied by each feature
  milestone at its own call sites.
- Blocks every subsequent screen milestone (M05–M09), all of which render inside `_app`'s `<Outlet>`.

## Open questions / judgment calls for the implementer

- The spec doesn't specify whether `SideNav` and `BottomNav` share a single "nav items" data
  structure or are built independently. Share one — computing the manifest-derived list twice
  invites the two navs to drift out of sync (e.g. one showing Notes before the manifest loads and
  the other not).
- §9's `/settings/:domain` "validate without a network call" requirement implies the manifest query
  must already be resolved (or at least attempted) by the time this route can be reached — since
  `_app`'s loader awaits auth bootstrap but not necessarily the manifest fetch, decide here whether
  `_app`'s loader also awaits `qk.dashboard.manifest()` (recommended: yes, given the nav itself
  needs it to render correctly on first paint anyway) rather than leaving `/settings/:domain` to
  guess at an unresolved cache.

## Verification

- Full keyboard traversal of the shell (skip link → nav → outlet → user menu) reaches every
  interactive element in logical DOM order (§21 A2, test case 48 — full coverage is M11's, but do a
  manual pass here).
- Manually toggle Light/Dark/System and confirm `data-theme` and `theme-color` update with no flash
  on reload.
- Resize through all five breakpoints and confirm the nav placement (side vs. bottom) and tile-grid
  column count (M05 territory, but the container query breakpoints are this milestone's) switch at
  the documented widths.
- 200% browser zoom and 320px width: shell remains usable, no horizontal scroll (§21 A12).
