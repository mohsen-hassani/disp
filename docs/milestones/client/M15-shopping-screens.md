# M15 — `shopping` screens (catalogue, lists, insights)

**Status:** Not started. The server half (`docs/milestones/server/M23-shopping.md`) is also unbuilt, so
this milestone cannot begin until `/api/shopping` exists and `openapi.json` has been regenerated —
`pnpm api:generate` is the first command of this milestone, not an afterthought at the end of it.
Unlike `M14`, where `plants` had shipped months earlier and the client was catching up, these two
are designed together; where they disagree about a path or a field name, **the server milestone
wins** and this file gets corrected.

**Scope:** `src/routes/_app.shopping.*.tsx` (6 route files) and their `-shopping-*.tsx` page
components, `src/components/shopping/` (11 components + one mutations hook), one line in
`src/modules/registry.ts`, new entries in `src/api/queryKeys.ts` and `src/api/queries.ts`,
regenerated `src/api/generated/`, `tests/unit/shopping/`, and `tests/e2e/shopping.spec.ts`.

Depends on **M13** (module nav contract) and **M17** (the server-side `client_nav` half), both
complete. Navigation, the nav icon, the ordering and the tile deep link are already solved and
**must not be re-solved here**: `computeNavSections` reads `client_nav` from the manifest,
`navigableDomains` (`src/modules/registry.ts:33-42`) intersects it with `MODULE_SCREENS`, and
`translateTileHref` (`src/components/tiles/tileLinks.ts:22-33`) turns the tile's `/api/shopping/…`
href into a route by stripping `/api`. **If you find yourself editing anything under
`src/components/layout/` or `src/components/tiles/`, stop** — the correct change is somewhere else.

Covers `TECHNICAL-SPEC-WEB.md` §1.2 and goal W5, extended to a third module. No amendment to the web
spec is required.

---

## 1. The two rules everything else serves

**Rule one: the product catalogue is global, and this client is the first line of defence against
duplicating it.** There is no per-user catalogue and no ACL on a product — `M23` §9.1 argues why —
so every near-duplicate someone creates is permanent, shared, and splits that product's price
history in two. The server's unique index on `name_normalized` catches exact collisions after
normalisation. It does not catch "Olive oil" versus "Olive Oil (extra virgin)", and nothing ever
will. Only the UI can, by showing the user what already exists **before** offering to create
something new. §5's `ProductCombobox` is the entire mitigation, which is why it gets more of this
document than any other component.

**Rule two: translations are asynchronous, so "not there yet" is a first-class state, not an empty
one.** A product created three seconds ago has no German name, and it is *correct* that it has none.
The server says so explicitly — `GET /lists/{id}/items/{id}` returns every one of the caller's
active languages, each carrying either a `text` or a `pending` marker (`M23` §8.3). Render the
pending marker. A UI that omits pending languages shows a user who configured three languages a
panel with one, and there is no way for them to tell that from the feature being broken.

Consequences, all of them load-bearing:

- **Never derive a translation client-side.** No fallback to the base name dressed up as a
  translation, no `??  product.name`. If it is pending, say pending.
- **Never compute a line total on the server's behalf and send it back.** `unit_price` is what the
  API stores; `unit_price × quantity` is display arithmetic and stays in the component.
- **Never issue two requests for "Update and Complete".** `M23` **S5**. One `PATCH` with
  `complete: true`. A `mutateAsync` chain here is a bug even when it works locally.
- **Never optimistically flip an item to bought.** `M23` **S6** pairs `has_bought` with a server
  timestamp; write the server's returned item into the cache, the way
  `usePlantMutations.ts:261-273` writes back the server's `interval` rather than predicting it.

`docs/milestones/server/M23-shopping.md` is the source of truth for every field, code and status on this
page. Read it before this one.

## 2. Routes

| Path | Route file | Page component | Title |
|---|---|---|---|
| `/shopping` | `_app.shopping.index.tsx` | `-shopping.tsx` | `Shopping · DISP` |
| `/shopping/lists/new` | `_app.shopping.lists.new.tsx` | `-shopping-list-new.tsx` | `New list · DISP` |
| `/shopping/lists/$listId` | `_app.shopping.lists.$listId.tsx` | `-shopping-list-detail.tsx` | dynamic |
| `/shopping/products` | `_app.shopping.products.index.tsx` | `-shopping-products.tsx` | `Products · DISP` |
| `/shopping/products/$productId` | `_app.shopping.products.$productId.tsx` | `-shopping-product-detail.tsx` | dynamic |
| `/shopping/insights` | `_app.shopping.insights.tsx` | `-shopping-insights.tsx` | `Insights · DISP` |

**These paths are not a design choice — they are the API paths minus `/api`.** `translateTileHref`
is a pure string rewrite (`tileLinks.ts:22-33`), so a tile deep-linking to
`/api/shopping/lists/{id}` becomes `/shopping/lists/{id}` and must land on a real route. Putting the
list detail at `/shopping/$listId` would look tidier and would break every tile link silently,
because a `null` from `translateTileHref` renders as no button rather than an error.

A route file exports **only** `Route`; the page component is a sibling `-name.tsx`, which the router
plugin ignores (the leading `-`) and which therefore takes plain props and is unit-testable without
a router. `autoCodeSplitting: true` (`vite.config.ts:33`) splits on the route file, so a fat page
component costs nothing until navigated to.

`$listId` and `$productId` loaders copy `_app.plants.$plantId.tsx:15-34` exactly: a module-scope
`UUID_RE` rejecting a malformed id with `throw notFound()` before any round trip, then
`ensureQueryData` in a `try`/`catch` that maps a 404 `ProblemDetail` to `notFound()` and rethrows
everything else, plus `notFoundComponent: NotFoundPage`.

**Any `beforeLoad` here must `ensureQueryData`, never `getQueryData`.** TanStack Router runs every
matched route's `beforeLoad` before any route's `loader`, so on a direct navigation a child can read
a cache the parent has not filled yet. This bit the settings route live (`CLAUDE.md`); do not
rediscover it.

`/shopping` and `/shopping/products` both take a `q` search param via `validateSearch`, collapsing
anything non-string to `undefined` and navigating with `replace: true` while the user types — the
`_app.plants.index.tsx:10-16` pattern.

## 3. Registration

One line, and it is the entire integration:

```ts
// src/modules/registry.ts:20
export const MODULE_SCREENS: ReadonlySet<string> = new Set(['notes', 'plants', 'shopping']);
```

**This will immediately fail `tests/unit/tiles/no-domain-literals.test.ts`** if the word "shopping"
appears anywhere under `src/components/tiles/` — that test derives its forbidden list from
`MODULE_SCREENS` and scans the directory as **raw text, comments included**. Module-specific code
goes in `src/components/shopping/`. It never goes in `tiles/`, not even in a comment explaining why
it isn't there.

What comes for free once that line lands, and should be *verified* rather than built: the sidebar
and bottom-nav entry (label, `shopping-cart` icon and order all arrive from the manifest), the tile
on the dashboard, the tile's nav button, and the settings panel at `/settings/shopping` — the last
of which is the interesting one, below.

**The settings screen is a verification task, not a build task.** `M23` §6.1 shapes the language
list as `list[{code, active}]`, and the generic `SchemaForm` already renders exactly that:
`fieldFor.tsx:90-105` accepts object-item arrays up to `MAX_NESTING_DEPTH`, and `ArrayWidget.tsx`
supplies the Add/Remove rows. Write the test, add the e2e step, and **do not build a bespoke
language editor**. If the generic form renders it badly, the fix is in `schema-form/` — where it
benefits every module — not in a `shopping/` special case.

## 4. API surface

Everything comes from `src/api/generated` via `pnpm api:generate`. Zero hand-written request shapes,
zero URL literals outside the generated SDK (goal W7). Query keys go in `src/api/queryKeys.ts`
alongside the existing `qk.plants` block; query options factories go in `src/api/queries.ts`. No
ad-hoc key literal anywhere.

```ts
shopping: {
  all: () => ['shopping'] as const,
  lists: (f: { archived?: boolean }) => ['shopping', 'lists', f] as const,
  list: (id: string) => ['shopping', 'list', id] as const,
  products: (f: { q?: string; category_id?: string }) => ['shopping', 'products', f] as const,
  product: (id: string) => ['shopping', 'product', id] as const,
  item: (listId: string, itemId: string) => ['shopping', 'item', listId, itemId] as const,
  categories: () => ['shopping', 'categories'] as const,
  priceHistory: (productId: string) => ['shopping', 'price-history', productId] as const,
  purchases: (f: { q?: string; since?: string }) => ['shopping', 'purchases', f] as const,
},
```

| Screen | Calls |
|---|---|
| Lists hub | `shoppingListsList` → `Page<ShoppingListOut>` |
| List detail | `shoppingListsGet` → list + items with embedded product summaries; `shoppingItemsAdd`, `shoppingItemsUpdate`, `shoppingItemsMove`, `shoppingItemsDelete`, `shoppingListsShare`, `shoppingListsShares`, `shoppingListsUnshare` |
| Item dialog | `shoppingItemsGet` → item + `translations: {lang, text, pending}[]` |
| Combobox | `shoppingProductsList` with `q` |
| Products | `shoppingProductsList`, `shoppingProductsCreate`, `shoppingProductsUpdate`, `shoppingProductsDelete`, `shoppingProductsSetImage`, `shoppingCategoriesList` |
| Insights | `shoppingAnalyticsPriceHistory`, `shoppingAnalyticsPurchases` |

`shoppingListsGet` returns items **with their product name, image URL and category already
embedded** — do not fetch products per row. The one thing it deliberately does *not* embed is
translations: those are per-item and only wanted when a dialog opens, so `shoppingItemsGet` is a
separate call made on open rather than a payload every list read carries.

Signed image URLs from `core.files` expire. `ProductThumbnail` handles that (§6), not the query
layer.

## 5. Screens

**Lists hub (`/shopping`).** The landing screen, because starting a shop is the common intent and
editing the catalogue is the rare one. Each list card shows name, item count, remaining-to-buy
count, and `updated_at`. Sections for active and archived, archived collapsed by default. Four
states, as every list in this app has: skeleton rows, error with retry, empty ("No lists yet"), and
empty-with-filters. `SavedDataLabel` when the data came from cache while offline. A prominent "New
list" action and a secondary link to Products.

**List detail (`/shopping/lists/$listId`).** The screen that matters. Header with the list name,
`created_at`/`updated_at`, a share affordance and an overflow menu (rename, archive, delete). Then
the add-item row — `ProductCombobox` plus Quantity and Unit price inputs, both optional, submitted
together. Then the items, unbought first, bought below in a collapsed "Bought (n)" group.

Each `ItemRow` carries the three actions from `M23` §8.1. **Move** and **Update and Complete** are
one request each; **Update** opens the same dialog as tapping the row. On a narrow viewport the row
collapses to name + quantity + a single tap target, with the three actions inside the dialog — three
buttons per row is unusable one-handed in a shop, which is the actual usage context.

> **The offline state is not hypothetical here; it is the modal experience.** `src/api/client.ts:75`
> rejects every mutation while offline with a synthetic `TypeError`, by design. A supermarket is
> where signal dies. So: `OfflineBanner` must be visible on this screen and not tucked into a
> corner, a failed submit must leave the user's typed quantity and price **in the form**, and the
> error copy must say the change was not saved rather than something ambiguous like "try again".
> Full offline queueing is out of scope (§8) — being honest about it is not.

**Item dialog.** Quantity, unit price, note, a derived line total shown read-only beneath the price,
and the translation panel. Two buttons: "Save" and "Save and mark bought", mapping to `complete`
omitted and `complete: true`. If the item is already bought, the second button becomes "Mark not
bought" (`complete: false`) and the dialog shows who bought it and when.

The translation panel is the language-practice feature and deserves care disproportionate to its
size: the base name first, labelled English, then one chip per language the *caller* has active.
A chip with no text yet reads "translating…" with `aria-live="polite"`, so the value being filled in
a moment later is announced rather than appearing silently. Chips are not interactive — this is
something to read while queueing, not a control.

**Move dialog.** A picker over the caller's writable lists, current list excluded. Two server
refusals must be rendered as specific inline copy, not a generic toast: `item_already_bought` ("This
was already bought — move it before marking it bought, or unmark it first") and `item_exists` ("That
list already has this product"). A generic "Something went wrong" here is a dead end, because both
have an obvious next action.

**Share dialog.** Email plus read/write, lifted from the notes sharing UI. `user_not_found` and
`cannot_share_with_self` map to inline field errors via `mapValidationErrors`.

**Products (`/shopping/products`).** The catalogue: debounced search, category filter, grid of cards
with thumbnail, name, category and unit. Create opens the same editor as edit.

**Product detail (`/shopping/products/$productId`).** Name, description, category, unit, image
upload, the full translation list (all languages, same pending treatment), and a compact price
history with a link into Insights. Delete is a soft delete and the confirm copy must say so — "It
stays in past lists and in your purchase history" — because `M23` **S9** means it genuinely does,
and a user who expects a hard delete will otherwise think it failed.

**Insights (`/shopping/insights`).** A product picker driving a price series, plus a purchase
search. The chart is a hand-written inline `<svg>` sparkline in `PriceSparkline.tsx` — **no charting
dependency is added**; the repo ships none and this screen does not justify the first. Points are
`(bought_at, unit_price)`; the accessible representation is the table beneath it, and the SVG is
`aria-hidden` with the table as the real content. Purchases with no recorded price appear in the
table flagged, never as a zero. Series in different currencies render separately and are never
summed.

## 6. Patterns to reuse, not reinvent

- **Mutations** — one `useShoppingMutations.ts`, shaped like `usePlantMutations.ts`: private
  `xOrThrow()` wrappers turning the generated SDK's `{data, error, response}` into a throw via
  `parseProblem`, so every mutation is `useMutation<Out, ProblemDetail, Vars>`; an exported
  `invalidateAffected(qc, listId)` (`usePlantMutations.ts:54-61`) covering the list prefix, the
  detail key and `qk.dashboard.tile('shopping.open_lists')`; and a `describeShoppingError(problem)`
  at the bottom (`:303`) that deliberately omits codes already surfaced inline beside a field.
- **Search lists** — `useInfiniteQuery` + `useDebouncedValue(input, 300)` + the `lastDispatchedRef`
  URL↔input reconciliation from `PlantList.tsx:44-62`, and an explicit "Load more" button. Never
  scroll-triggered.
- **Images** — `ProductThumbnail.tsx` reuses `PlantThumbnail.tsx:44-64` verbatim in behaviour: a
  signed URL can expire between render and load, `<img onError>` cannot see the status code, so it
  retries **once** by calling `invalidateAffected` to re-mint the URL, resets that flag on
  `imageUrl` change, and otherwise renders a placeholder icon. Never a broken `<img>`.
- **Upload** — `PhotoUpload.tsx`'s shape: hidden `<input type="file">` behind a visible button,
  client-side type and 2 MiB size pre-check for a fast error, still handling server rejection,
  disabled via `useOfflineState()`.
- **Forms** — `react-hook-form` + `zodResolver`, 422 mapping through
  `mapValidationErrors(serverErrors, FIELD_SET)` → `setError`/`setFocus` (`src/lib/`).
- **Dialogs** — Radix `Dialog.Root`/`Portal`/`Overlay`/`Content`, `aria-labelledby={useId()}`, and
  `onCloseAutoFocus` restoring focus to a `useRef` trigger when the opener was a menu item that
  unmounted (`-plant-detail.tsx:151-154`).
- **Styling** — Tailwind semantic tokens only (`surface`, `text-muted`, `border`, `accent`,
  `danger`, …). No raw hex, no arbitrary values. Button classes are module-local `const` strings, as
  every existing component does — `src/components/ui/` is empty and this milestone does not fill it.

### 6.1 `ProductCombobox` — the one thing with no precedent

There is no combobox in this codebase and no dependency that supplies one. `package.json` has no
`cmdk` and no `@radix-ui/react-popover`, and **neither should be added**: the WAI-ARIA combobox
pattern requires focus to stay in the text input while a listbox is navigated, which is precisely
what a Radix popover takes away. Build it as an input plus an absolutely-positioned
`role="listbox"`, which is both the smaller change and the correct one.

Requirements:

- `role="combobox"` on the input with `aria-expanded`, `aria-controls`, and `aria-activedescendant`
  pointing at the focused option's id. Focus never leaves the input.
- ↑/↓ move the active option, Enter selects, Escape closes and leaves the typed text, Tab closes and
  commits nothing.
- Debounced server search (300 ms), results ranked prefix-before-substring by the server.
- **Existing matches render above the create affordance, always** — and the create row is disabled
  while results are still loading. Offering "Create *Olive Oil*" next to an unresolved spinner is
  how the catalogue acquires its second olive oil. This is rule one from §1, expressed as a layout
  constraint.
- The create row posts through `shoppingItemsAdd`'s `new_product` branch: one round trip creates the
  product and adds the item. It does **not** call `shoppingProductsCreate` and then add.
- Announce result counts via `aria-live="polite"`, and pair with a visible `<label>`.

## 7. Verification

Unit tests in `tests/unit/shopping/`, with a `testUtils.tsx` exporting `renderShopping()` that seeds
`queryClient.setQueryData(qk.dashboard.manifest(), mockManifest())` — without the manifest every
component believes nothing is navigable. MSW handlers extend `tests/mocks/handlers.ts`. Overall
coverage stays ≥80%; `src/auth/` and `src/components/schema-form/` keep their ≥95%, and adding a
settings-panel test here should push schema-form's array path up rather than down.

Cases that must exist, because they encode the invariants rather than the markup:

1. **Duplicate defence.** Typing a query that returns matches renders those matches *above* a
   create row, and the create row is disabled while the query is pending. Assert DOM order, not just
   presence.
2. **One request to complete.** Clicking "Save and mark bought" issues exactly one `PATCH` whose
   body carries quantity, price and `complete: true` together. Assert the request count is 1 —
   asserting only the final state passes against a two-call implementation.
3. **Pending translations render.** An item whose `translations` include `{lang: 'DE', pending:
   true}` shows a "translating…" affordance for DE, and DE is not omitted. Assert `aria-live` is
   present on the region.
4. **No client-side fallback.** A pending language never renders the base name. Give the fixture a
   distinctive base name and assert it appears exactly once.
5. **Move refusals are specific.** A 409 `item_already_bought` and a 409 `item_exists` each render
   their own copy inside the dialog, and the dialog stays open.
6. **Expired image URL.** An `onError` on the thumbnail triggers exactly one invalidation, and a
   second `onError` renders the placeholder rather than invalidating again.
7. **Route paths match the API.** A unit test asserting `translateTileHref('/api/shopping/lists/x',
   new Set(['shopping']))` equals `'/shopping/lists/x'`, and that this equals a real route path.
   Cheap, and it catches the one mistake §2 warns about.
8. **Offline.** With `useOfflineState()` true, the item form's submit is disabled, the banner is
   visible, and typed values survive a rejected submit.
9. **Settings panel.** The manifest's `shopping.preferences` schema renders an array of objects with
   working Add/Remove, and a freshly added row does not show a validation error before it is touched
   (the `ArrayWidget.tsx:71` `append({})` behaviour — `M23` §6.1).

`tests/e2e/shopping.spec.ts`, against the real stack: sign in → add two languages in settings →
create a product → create a list → add the product via the combobox → set price and mark bought →
open the item and see translations (asserting the *pending or filled* states, never a fixed
timing) → move it to a second list → check Insights shows the purchase. Include an
`@axe-core/playwright` pass on the list-detail screen with the item dialog open, since the combobox
and the dialog are the two least conventional things in this milestone.

Commands, all from `clients/web/`:

```
pnpm api:generate && pnpm api:check
pnpm lint && pnpm typecheck
pnpm test --run --no-file-parallelism
pnpm test:e2e
pnpm check:budget
```

**Manual:** the combobox on a real phone, one-handed, in a shop or a convincing imitation of one.
Keyboard-only navigation of the combobox and the item dialog. And one deliberate run with the
device offline mid-list to confirm the copy in §5's blockquote actually reads the way it should.

## 8. Explicit non-goals

Do not build offline mutation queueing — `src/api/client.ts` blocks mutations offline deliberately
(§M09), a queue needs conflict resolution this module has not specified, and shipping a half-queue
that loses writes is worse than a clear refusal; the honest surfacing required in §5 is the whole
scope here. Do not add a charting library for one sparkline. Do not build a bespoke settings editor
for languages (§3). Do not add barcode scanning, recipes, store selection, currency conversion, or
cost-splitting — all deferred server-side in `M23` §14, and a client that renders them would be
inventing API. Do not search products by translated name; the server does not support it (`M23`
§14). Do not optimistically update purchase state (§1). Do not put anything domain-specific in
`src/components/tiles/` (§3). And do not fill `src/components/ui/` with primitives as a side quest —
extracting shared button classes is a real refactor worth doing on its own, across all three
modules, not smuggled into this one.
