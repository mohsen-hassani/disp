# M13 — Manifest-driven module navigation

**Status:** Complete

**Scope:** `clients/web/src/lib/icons.ts` (new), `clients/web/src/modules/registry.ts` (new),
`clients/web/src/hooks/useNavigableDomains.ts` (new),
`clients/web/src/components/layout/{navItems.ts,SideNav.tsx,BottomNav.tsx,AppShell.tsx}`,
`clients/web/src/components/tiles/{tileLinks.ts,TileCard.tsx,TileItemRow.tsx,TileActionButton.tsx,tileButton.ts}`.

Implements WEB-SPEC amendment A3 (§1.2, §12.2, §13.3, §13.6, §13.7). The backend half is
`milestones/server/M17`.

---

## The rule this milestone establishes

**Navigation is the intersection of two facts, and neither one alone is sufficient:**

| | source | answers |
|---|---|---|
| policy | `manifest.client_nav` | should this module appear, with what label/icon/order? |
| capability | `MODULE_SCREENS` | do the screens actually exist in this client? |

M04's `MODULE_ROUTES` conflated these — one hard-coded map carried the label, the icon, the path
*and* the "does it exist" answer. Splitting them moves all presentation to the server while keeping
§12.2's original honesty rule literally intact: the client still never links to a screen it doesn't
have. A module declaring `client_nav` that this client can't render is dashboard-only, exactly as if
it had declared nothing.

`MODULE_SCREENS` is a bare `ReadonlySet<string>` — no label, no icon, no path. That is the point:
there is nothing left in it to drift out of sync with the server.

## What changed, and the parts that were not obvious

**`computeNavItems` → `computeNavSections`.** Returns `NavSection[]` (`primary` / `modules` /
`system`) instead of a flat `NavItem[]`. Only `modules` carries a visible heading, and the section is
omitted entirely when empty — a "Modules" heading with nothing under it advertises a capability the
install doesn't have. It takes the full `ModuleManifestOut[]` now, not a `string[]` of domains,
since the label/icon/order all come from the manifest entry.

It also takes an optional `screens` set. Without that seam the ordering tests are vacuous: with only
`notes` in `MODULE_SCREENS`, a sort over two modules can never demonstrate anything, because the
filter leaves one survivor either way. Injecting the set lets ordering and filtering be tested
independently of which domains this client happens to ship today.

**SideNav renders sections; BottomNav flattens them.** Grouping is a desktop affordance — §12.3's
4-slot bar has no room for headings. `flattenNavSections` runs before the existing `desktopOnly`
filter and `MAX_SLOTS` logic, which are otherwise untouched. Worth noting the overflow rule is now
genuinely reachable: Dashboard + Settings + two modules is exactly 4, so a third module with
screens is what finally trips the "More" sheet.

**`translateTileHref` had to lose its static import.** This was the one genuinely invasive edit.
The function closed over `MODULE_ROUTES` at module scope; reachability is now runtime manifest data,
so the navigable-domain set is passed in as a second argument, sourced from `useNavigableDomains()`
(manifest query ∩ `MODULE_SCREENS`, memoised because it returns a fresh `Set`). `TileItemRow` calls
the hook and forwards it. The transform stays a pure string rewrite, which remains sound only
because routes are always `/<domain>/…` (M17's derived-namespace decision).

**The tile nav button derives its domain from `spec.key.split('.')[0]`.** No literal, no map. It
renders only when that domain is navigable, so the honesty rule holds at tile level too. The footer
condition changed from `actions.length > 0` to `actions.length > 0 || navPath`, and the button class
moved to `tiles/tileButton.ts` so the `<Link>` and the action `<button>`s sitting beside it can't
drift apart.

## The guardrail, repointed

`tests/unit/tiles/no-domain-literals.test.ts` (M05's test case 27) scans every file under
`src/components/tiles/` as raw text and fails if any known module domain appears as a whole word —
**including inside a comment**. Its domain list came from `Object.keys(MODULE_ROUTES)`; it now comes
from `MODULE_SCREENS`.

That is not a mechanical rename. It means the moment `plants` is registered (M14), the word
`plants` becomes forbidden in that directory too — the generic mechanism isn't merely documented as
generic, it's mechanically pinned as each new module arrives.

## Test-infrastructure change worth knowing about

`renderTile` and `renderNotes` now seed the manifest into the query cache:

```ts
queryClient.setQueryData(qk.dashboard.manifest(), mockManifest());
```

Without it every component under test sees an empty manifest on first paint and renders the
correct-but-unhelpful "nothing is navigable" state, so `TileItemRow`'s link assertions fail for the
right reason at the wrong time. Seeding reproduces the real guarantee: `routes/_app.tsx`'s loader
awaits that query before any of this mounts. `tests/mocks/fixtures.ts`'s `mockManifest` and
`AppShell.test.tsx`'s local fixture both gained `client_nav`, matching what the real backend now
sends.

## Verification

- `pnpm test --run --no-file-parallelism` — 53 files / 238 tests, exit 0, coverage thresholds met.
- `pnpm lint` (eslint + prettier) and `tsc --noEmit` clean.
- **Note on the suite's flakiness, which predates this milestone:** run the suite in parallel on a
  loaded machine and a shifting handful of `userEvent`-driven interaction tests time out at 5000ms —
  three consecutive runs on an identical tree gave 0, then 1, then 4 failures, including files this
  milestone never touched (`ToastProvider.test.tsx`). It is CPU contention, not a regression, and
  `--no-file-parallelism` is green every time. Worth fixing properly (a raised `testTimeout`, or
  capping worker count) rather than re-diagnosing each time it surfaces.

## What this does *not* do

`plants` is still not in the nav after this milestone, and that is the correct outcome, not an
oversight: its manifest declares `client_nav`, but `MODULE_SCREENS` has no `plants` entry because
the screens don't exist yet. It lights up with **zero further contract work** the moment M14 ships —
which is the whole claim this milestone makes, and the cheapest possible way to test it.
