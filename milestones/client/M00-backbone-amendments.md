# M00 — Backbone amendments (backend prerequisites for the web client)

**Status:** Complete

**Scope:** `src/disp/core/dashboard.py`, `src/disp/core/settings_store.py`, `src/disp/core/notifier.py`,
`src/disp/core/contract.py` (read-only reference — no signature change), new `tests/core/test_dashboard.py`,
plus two pre-existing tests updated for a newly-visible `"core"` manifest entry
(`tests/cli/test_cli_commands.py::test_modules_plain_and_json`,
`tests/core/test_plugin_proof.py::test_hello_module_appears_in_manifest_and_renders_tile`). No new
module, no new package. This milestone touches the **backend**, not `clients/web/`.

Covers TECHNICAL-SPEC-WEB.md §3 (Required backbone amendments), amendments A1 and A2. A3 is
explicitly declared out of scope here (see below). Also documents a spec-vs-reality correction to
§7.1 that gates M02/M03.

---

## Why this is a client milestone even though it changes backend code

TECHNICAL-SPEC-WEB.md §3 states plainly: *"Each is small and additive... MUST be implemented before
the corresponding client features."* A1/A2 are prerequisites for M06 (generic settings rendering,
§14) specifically — `SchemaForm` cannot render anything, and secret fields cannot be identified at
all, without them. Building M06 against today's backend would mean building against a manifest that
has no `schema` field whatsoever. This milestone must land, and be verified against a live
`GET /api/dashboard/manifest` response, before M06 starts.

## Current state (verified against the actual code, not assumed from the spec)

**A1 — not built.** `SettingsPanelSpec` (`src/disp/core/contract.py:36-43`) already carries
`schema_model: type[BaseModel]` as an internal-only field:

```python
class SettingsPanelSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    key: str = Field(pattern=KEY_RE)
    title: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    schema_model: type[BaseModel]
    scope: Literal["user", "global"] = "user"
```

But `SettingsPanelOut`, the response model the manifest endpoint actually returns
(`src/disp/core/dashboard.py:27-34`), has no `schema` field:

```python
class SettingsPanelOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    title: str
    description: str | None
    scope: Literal["user", "global"]
```

and `get_manifest()`'s panel-mapping comprehension (`dashboard.py:96-104`) never calls
`model_json_schema` — it only forwards `key`/`title`/`description`/`scope`. Confirmed via a
repo-wide grep: zero calls to `model_json_schema` anywhere in `src/disp/`.

**A2 — half built.** Secret fields are already declared today via a `json_schema_extra` convention:

```python
# src/disp/core/notifier.py:43 (existing usage)
urls: list[str] = Field(json_schema_extra={"secret": True}, ...)
```

```python
# src/disp/core/settings_store.py:25
SECRET_FIELD_MARKER = "secret"  # noqa: S105 - json_schema_extra convention key, not a credential
```

read back via `_field_is_secret()` (`settings_store.py:174-176`) and used only in
`GET`-masking/`PUT`-validation logic (`:198-209`, `:288-290`) — i.e., entirely server-internal. Since
A1 doesn't exist, this marker never reaches a JSON Schema document at all today, let alone as
`x-secret`.

**A3 — not present, and per §3 non-blocking.** `GET /api/notes` returns `Page[NoteOut]`
(`src/disp/modules/notes/router.py:18`), and `Page[T]` (`src/disp/core/pagination.py:35-38`) is:

```python
class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None
    has_more: bool
```

No `total`. This is a deliberate property of cursor pagination (a `total` requires a `COUNT(*)`
query that cursor pagination exists specifically to avoid), so **do not add it** — §3's own text
says the implementer "MUST NOT add this to the backend unilaterally." M08 (notes screens) must be
built to work without a count, per the spec.

## What to build

### A1: serialize `schema_model` into the manifest

In `dashboard.py`:

1. Add `schema: dict[str, Any]` to `SettingsPanelOut`.
2. In `get_manifest()`'s panel comprehension, compute
   `panel.schema_model.model_json_schema(mode="serialization")` and inline any `$defs` references
   so the emitted document is self-contained (a client-side JSON Schema resolver is out of scope
   per the client spec's Appendix B, which expects `$ref` to already point within the same
   document — inlining, not just "keep resolvable", is the safer reading, since the client spec's
   `$ref` row says "resolve and recurse" against `$defs` in the *same document*, which
   `model_json_schema()` already produces by default. Confirm no cross-model `$ref` escapes the
   panel's own schema before calling this done — Pydantic v2 keeps `$defs` local to the call by
   default, so this should be automatic, but assert it with a test rather than trusting it.)
3. `mode="serialization"` (not the default `"validation"`) per §3's literal instruction — this
   matters because a `validation`-mode schema for a field with a custom serializer could differ
   from what the client will actually receive/round-trip.

### A2: carry the secret marker into the schema as `x-secret`

`json_schema_extra` dict entries on a `Field(...)` already surface as sibling keys on that
property's JSON Schema object when `model_json_schema()` runs — so `{"secret": True}` becomes
`{"secret": true}` in the output today, automatically, once A1 exists. Two implementation choices,
pick one and document it in code:

- **(a) Rename the marker** from `"secret"` to `"x-secret"` in every existing
  `json_schema_extra={"secret": True}` call site (`notifier.py:43` and any other module that
  declares a secret setting) and in `SECRET_FIELD_MARKER`/`_field_is_secret()`
  (`settings_store.py:25,174-176`). Simplest, single source of truth, but touches every settings
  schema in the codebase (currently just `notifier.py`, per grep — small blast radius today).
- **(b) Post-process** the serialized schema in `dashboard.py` after A1's `model_json_schema()`
  call, walking `properties` and copying `secret: true` → `x-secret: true` (and optionally
  stripping the internal `secret` key so it isn't doubly present in a public API response). Keeps
  `settings_store.py`'s internal convention unchanged, at the cost of a second pass over each
  schema at manifest-build time.

Recommend **(a)** — cheaper, avoids two names for the same fact, and the marker is not
security-sensitive (it's a convention key, not a secret value), so renaming it is a pure rename with
no compatibility burden since nothing external depends on the current internal key name yet.

### Explicitly not building here

- A3 (`total` on notes list) — out of scope, see above.
- Any change to `SettingsPanelSpec` itself, `contract.py`'s shape, or the settings `GET`/`PUT`
  routes' masking logic (`***` sentinel behavior) — those are unaffected; this milestone only adds a
  field to the *manifest* response.

## Spec-vs-reality correction: `X-Requested-With` header value

TECHNICAL-SPEC-WEB.md §7.1 instructs the client to send `X-Requested-With: mystuff` on
`/auth/refresh` and `/auth/logout`. That literal value is **wrong for this codebase.** The backend's
actual CSRF check (`src/disp/core/auth/routes.py:79`, enforced at `:317` and `:409`) requires the
exact string `"disp"`:

```python
# src/disp/core/auth/routes.py (existing)
def _require_csrf_header(request: Request) -> None:
    if request.headers.get("X-Requested-With") != "disp":
        raise ...
```

## Dependencies

None — this is the first milestone; it only requires the already-complete backend from
`milestones/server/M00-M19`.

## Blocks

- **M06** (settings rendering) hard-depends on A1 and A2 landing and being verified against a live
  `GET /api/dashboard/manifest` call before it can be implemented, let alone tested end-to-end.
- **M02** and **M03** must use the corrected `X-Requested-With: disp` value documented above.

## Verification

- `./dev test` — add a manifest test asserting a panel with a `schema_model` that has a secret
  field produces a `schema` object whose corresponding property carries `"x-secret": true`, and that
  a panel's schema round-trips through `json.dumps` (proving no unresolved `$ref` or non-serializable
  value leaked through).
- `./dev openapi` — regenerate `openapi.json` and manually inspect that `SettingsPanelOut.schema` is
  present in the OpenAPI component schema (proves the new field is visible to the client codegen in
  M02, not just to a live JSON response).
- `./dev lint` — ruff/mypy clean.
- Manual: hit `GET /api/dashboard/manifest` against a running dev server with the `core.notifier`
  panel registered and confirm the `urls` property in its `schema` shows `"x-secret": true`.

---

## Implementation notes (this milestone is now built)

### A third gap found while implementing A1: core-registered panels never reached the manifest at all

Auditing `get_manifest()` to add the `schema` field surfaced a bug that predates this milestone and
is independent of A1/A2: `core.notifier` — the only settings panel that exists anywhere in this
codebase today — is registered via `Registry.register_core_settings_panel()`
(`app.py:150`, called unconditionally in `create_app()`), which inserts it directly into
`registry.settings_panels`. But `get_manifest()` builds its response by walking `registry.modules`
(populated only by `disp.modules/*` discovery) and reading each `dm.manifest.settings_panels` —
`core` is never a discovered module, so this loop silently skipped `core.notifier` entirely.
`GET /api/settings/core` already worked (it resolves panels via
`registry.settings_panel_for_domain()`, which does read `registry.settings_panels`), so the gap was
invisible from that route alone — only the *manifest* was blind to the panel's existence. Since A1's
whole point is giving the client a schema to render, and `notes` (the only discovered module) has
`settings_panels=()`, without fixing this there would have been no real panel anywhere in the
manifest to verify A1 against end-to-end.

**Fix:** `get_manifest()` now tracks which panel keys were already emitted via the per-module loop,
then appends a synthetic `ModuleManifestOut(domain="core", name="Core", ...)` entry containing every
panel left over in `registry.settings_panels` (currently just `core.notifier`). This is why the
manifest's `modules` list now includes a `"core"` domain in addition to whatever real modules are
discovered — two pre-existing tests asserted an exact domain set and needed updating
(`test_modules_plain_and_json`, `test_hello_module_appears_in_manifest_and_renders_tile`), which is
the correct fix (the new domain reflects real, previously-hidden capability) rather than a symptom
of anything broken.

### A1 implementation detail: field aliasing

`SettingsPanelOut.schema` can't be a literal Python attribute name — Pydantic v2's `BaseModel` has a
deprecated `.schema()` method, and a field named `schema` shadows it (`UserWarning` at class
definition time, not a hard error, but a warning on every response the client would see in server
logs). Used `schema_: dict[str, Any] = Field(alias="schema")` instead: FastAPI's response
serialization defaults to `by_alias=True`, so the wire-level JSON key is still exactly `"schema"` as
§3 requires, confirmed against the regenerated `openapi.json`'s `SettingsPanelOut` component (its
`required` list reads `["key", "title", "description", "scope", "schema"]`).

### A2 implementation: option (a), rename the marker

Took the milestone's own recommendation: `SECRET_FIELD_MARKER` in `settings_store.py` is now
`"x-secret"` (was `"secret"`), and `notifier.py`'s `urls` field's `json_schema_extra` was updated to
match. `_field_is_secret()`'s logic is unchanged — it just reads a differently-named key now, so
existing GET/PUT masking behavior (tested by `tests/core/test_settings_store.py` and
`tests/core/test_settings_routes.py`) needed no changes and all of it still passes. A repo-wide grep
confirmed `notifier.py` was the only call site using the old marker, so the blast radius was exactly
as small as anticipated.

### Verification actually performed

- `./dev lint` — clean (ruff, ruff format, mypy).
- `./dev test` — full suite: 135 passed. Overall coverage 86.52% (gate: ≥85%).
- `./dev openapi` — regenerated; confirmed `SettingsPanelOut.schema` present and required in the
  OpenAPI component schema.
- New `tests/core/test_dashboard.py` covers: `notes` still appears with `settings_panels: []`;
  `core.notifier` now appears under a `"core"` domain entry; its `urls` property carries
  `"x-secret": true` (and not the old `"secret"` key); and `channels` (`list[ChannelConfig]`)
  resolves through a `$ref` whose target lives in that same panel's own `$defs` block, confirming
  Pydantic's default local-`$defs` behavior holds rather than just assuming it.
- The `X-Requested-With` correction and A3 (notes `total`) required no backend changes, as
  documented above — nothing further to verify on the backend side for those.
