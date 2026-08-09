# M17 — Module client-surface contract

**Status:** Complete

**Scope:** `src/disp/core/contract.py`, `src/disp/core/dashboard.py`,
`src/disp/modules/{notes,plants}/manifest.py`, `tests/core/test_contract.py`,
`tests/core/test_dashboard.py`, `tests/core/test_plugin_proof.py`.

Amends TECHNICAL-SPEC.md §8.1/§8.2 and TECHNICAL-SPEC-WEB.md §12.2/§13.6/§13.7 (amendment A3).
The client half is `milestones/client/M13`.

---

## Why

`plants` shipped a `plants.due` tile and nothing else reachable: no nav entry, no screen, and its
tile items rendered as dead plain text. That was the spec working as written — WEB-SPEC §12.2 made
navigation depend on a **hard-coded client-side `MODULE_ROUTES` map**, so every module with a screen
meant editing a shared shell constant.

That is the same "one hard-coded list per new module" pattern the backend already eliminated for
Alembic branches (see `CLAUDE.md`, "Adding a module: branch registration is one line now"). A
module already declares its tiles, settings panels, scheduled jobs and notification types in its own
manifest; its client surface was the one capability it could not declare.

## What was added

Two frozen specs in `contract.py`, both optional with defaults so no existing manifest or test
fixture breaks (every model here is `frozen=True, extra="forbid"`):

- **`ClientNavSpec`** → `ModuleManifest.client_nav`. `label`, `icon` (a kebab-case lucide *name*),
  `order`, and an advisory `routes` tuple.
- **`TileNavSpec`** → `TileSpec.nav`. `label` plus a sub-path, rendering a navigation button in the
  tile's footer.

`ModuleManifestOut` in `dashboard.py` gained `client_nav`, populated from the manifest. `TileSpec`
is reused directly as its own wire model, so `TileSpec.nav` reached the client with no mapping code
at all — the same property that makes tile specs cheap to extend.

## Resolved design questions

**The route namespace is derived, never declared.** `ClientNavSpec` has no `base_path`. The client's
`translateTileHref` is a pure string rewrite — strip `/api`, keep the rest — so the UI path *must*
equal the API path minus `/api`. A module that could declare `base_path="/garden"` for domain
`plants` would silently break every tile deep link it ships. Removing the freedom removes the bug
class; routes are always `/<domain>/…`.

**`nav` belongs on `TileSpec`, not `TileData.actions`.** `notes`' `QUICK_ADD_ACTION` is attached at
render time in `tiles.py` because it is a *mutation* whose availability could vary per user. A nav
button is static structure, identical for every render. `TileAction` also cannot express it at all:
its `method` is `Literal["POST", "PATCH", "DELETE"]`, a mutation verb with no navigation case.
Putting it on the spec also means it costs nothing per tile render.

**`routes` is advisory, and says so.** The server cannot ship React, so this field can never *make*
a route exist. It documents the module's intended URL surface for a client-side conformance check.
Keeping it optional and explicitly non-enforcing is more honest than pretending the manifest
controls the client's router.

**Two new validator rules**, both in a second `model_validator` on `ModuleManifest`:

- a `TileSpec.nav` without `client_nav` is rejected — the button would link into a namespace the
  module never claimed;
- an absolute `client_nav.routes` entry is rejected, with a message naming the likely mistake
  rather than echoing the regex.

Note the existing `_validate_key_prefixes` loop does **not** cover new collections; any future
manifest field needs its own explicit check.

## A test that was removed, and why

`tests/core/test_plugin_proof.py::test_no_core_file_was_modified_to_add_the_hello_module` ran
`git status --porcelain -- src/disp/core` and failed on any tracked modification. That check did not
test the property in its own name: it asserted *"the working tree has no uncommitted core changes"*,
which is a fact about what the developer is currently doing, not about the `hello` module. It could
never distinguish "core was edited to make a module work" (what §22.4 forbids) from "core was
edited for its own reasons", and it fired on the first deliberate core change anyone made — this
one.

The git block was deleted; the file-location assertion it sat on top of remains, and the real proof
is the test above it: a module core has no knowledge of surfaces through the live HTTP API by
convention-based discovery alone.

**Generalisable lesson:** a guard test whose assertion is *broader* than its name is a
false-positive generator. It looks like a safety net right up until the first legitimate change in
its blast radius, at which point the pressure is to weaken the real invariant to get green. Assert
the property, not a proxy that happens to correlate with it today.

## Verification

- `./dev test` — 182 passed, 88% coverage (gate ≥85%).
- New `tests/core/test_contract.py` covers both validator rules, the defaults, the icon-name
  pattern, and the common case of a tile with no nav needing no `client_nav`.
- `tests/core/test_dashboard.py` gained two cases: the manifest exposes `client_nav` and
  `tiles[].nav`, and the synthetic `core` domain reports `client_nav: null` (a non-null value there
  would put a dead "Core" entry in the client's navigation).
- `./dev openapi` + `pnpm api:generate` — `clients/web/src/api/generated/` is committed and
  `pnpm api:check` is a CI drift gate, so the regenerated client had to be committed with this.

Pre-existing and untouched: three ruff failures in `src/disp/modules/notes/service.py`
(`I001`, two `UP031`) that are present on a clean tree.
