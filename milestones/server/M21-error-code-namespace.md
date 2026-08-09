# M21 — error code namespace

**Status:** Complete

**Scope:** every `code` the API emits. `src/disp/core/errors.py` (new `ERROR_CODE_RE` +
`validate_error_code`), 59 raise sites across `src/`, 53 assertions across `tests/`, 65 literals across
`clients/web/`, and the documentation that registers them. No behaviour change beyond the wire value of
`code` and a new startup-time guard.

**Amends** `TECHNICAL-SPEC.md` §17.4 and Appendix A, and `TECHNICAL-SPEC-WEB.md` §7.2/§7.3/§8.4/§8.6.

---

## Why

The platform had **three** error-code shapes coexisting and nothing to say which was correct:

| Shape | Examples | Count |
|---|---|---|
| `<domain>.<error>` | `auth.token_expired`, `notes.not_found`, `acl.forbidden` | 38 |
| bare | `rate_limited`, `validation_error`, `internal_error`, `http_error` | 4 |
| *(proposed)* `core.<subsystem>.<error>` | `core.files.too_large` in `M18-files.md` | — |

`AppError.code` was an unvalidated `str`. Appendix A said "New codes require a specification amendment"
and nothing enforced it, so the registry drifted from the code in three separate directions at once
(below). The immediate trigger was `M18-files.md` proposing a third shape without anyone noticing it
matched neither of the two already in use — which is the real problem, because the same thing will
happen to `M19` and `M20` and every module after them.

There was also a subtler cost. The platform has a **second** dotted namespace — `KEY_RE`
(`src/disp/core/contract.py:17`) for tile keys, job names, settings-panel keys and notification types —
and the two were indistinguishable on sight:

```
notes.not_found     an error code
notes.latest        a tile key
plants.no_image     an error code
plants.daily_check  a scheduled job name
```

Nothing but context told them apart, and a reader of one line of code could not know which registry to
look in.

## What changed

Every code is now **three segments**, `<realm>.<subsystem>.<error>`:

```
core.<subsystem>.<error>     core.auth.token_expired, core.acl.forbidden
modules.<domain>.<error>     modules.notes.not_found, modules.plants.no_image
core.platform.<error>        raised by the exception handlers, belonging to no domain
```

Segment count now distinguishes the two namespaces: **error codes have three, manifest keys have two.**

### The mapping

| Before | After |
|---|---|
| `auth.*` (21) | `core.auth.*` |
| `acl.forbidden` | `core.acl.forbidden` |
| `pagination.invalid_cursor` | `core.pagination.invalid_cursor` |
| `dashboard.tile_not_found` | `core.dashboard.tile_not_found` |
| `settings.*` (2) | `core.settings.*` |
| `notes.*` (3) | `modules.notes.*` |
| `plants.*` (9) | `modules.plants.*` |
| `rate_limited`, `validation_error`, `internal_error`, `http_error` | `core.platform.*` |

`core.platform` is the subsystem for codes the exception handlers raise themselves (§17.4). They are
core's, but they belong to no domain — `validation_error` is not an auth concern or a notes concern.
Giving them a subsystem rather than leaving them bare is what makes the shape uniform, so a client can
split on `.` unconditionally and a regex can enforce it.

### The guard

```python
# src/disp/core/errors.py
ERROR_CODE_RE = re.compile(r"^(core|modules)\.[a-z][a-z0-9_]{1,31}\.[a-z][a-z0-9_]{1,63}$")

def validate_error_code(code: str) -> str: ...
```

Called from **both** `AppError.__init__` and `problem_response`. Two call sites, deliberately: the four
handler-raised codes never pass through `AppError` at all — `_handle_validation_error` and friends call
`problem_response` directly — so validating only in the exception class would leave exactly the codes
that drifted furthest unguarded.

Validation at construction, not at response time: a bad code should break the test that raises it, not
appear in front of a client. `tests/core/test_errors.py::test_malformed_error_codes_are_rejected`
pins all four bad shapes (two-segment, bare, four-segment, wrong realm) plus casing and empty segments.

## Resolved questions

**Why not reuse `KEY_RE`?** Because the whole point is that these are *different* namespaces. `KEY_RE`
is `^[a-z][a-z0-9_]{1,31}\.[a-z][a-z0-9_]{1,63}$` — exactly one dot, and `ModuleManifest` additionally
requires every key to be prefixed with the module's own domain. Error codes need a realm segment that
manifest keys must not have, and core-owned codes (`core.pagination.invalid_cursor`) have no module
domain to prefix with. Sharing the regex would have forced one of the two namespaces to bend.

**Why `modules.` rather than the bare domain?** `plants.no_image` was already unambiguous as a string.
But the realm segment is what lets a reader tell an error code from a manifest key without knowing the
codebase, and it makes the core/module boundary visible at the point of use — a module surfacing
`core.files.too_large` unchanged (which `M18` requires) reads obviously as *not mine*.

**Hard cutover, no dual-emit.** Server, web client and the `disp` CLI ship from one repo at one version;
there is no independently-deployed consumer to keep compatible. A transition window would have meant
emitting both shapes, or a translation layer, for a consumer that does not exist.

**Frozen build logs left alone.** `milestones/server/M00`–`M17` and `milestones/client/M00`–`M14` record
what was built at the time and still quote the old shape. Rewriting them would falsify the record;
leaving them silently is how `M18` came to cite a deleted file. The compromise is a pointer in
`CLAUDE.md` (loaded every session) saying those logs are historical and Appendix A is current. The live
specs — `M18`, `M19`, `M20` — were updated.

## Bugs found on the way

Three, all pre-existing, all surfaced by having to enumerate the codes exhaustively for the first time:

1. **`core.platform.http_error` was emitted but never registered.** `errors.py`'s `HTTPException`
   handler has always produced `http_error`; Appendix A never listed it, despite opening with "Every
   `code` the API may emit." Now registered.

2. **`core.settings.decryption_failed` is registered but never raised.** `settings_store.py:158` logs a
   `settings_decryption_failed` *event* on a decryption failure but emits no problem response with that
   code, while the web client carries a live branch for it (`clients/web/src/api/queries.ts`) and
   `TECHNICAL-SPEC.md` §15 says it MUST "surface as `500 core.settings.decryption_failed` — never as a
   silent `None`." So the spec, the client and the server disagree. **Left as-is and flagged in
   Appendix A**: fixing it means either raising the error or deleting the entry, and both are behaviour
   changes that do not belong in a rename.

3. **Appendix A silently omitted all eight `plants.*` codes.** Not drift, as it first appeared —
   `plants` registers them in its own `TECHNICAL-SPEC.md` §18, and `learning` reserves a §24 for the
   same purpose. The convention was real but unwritten. Appendix A now states it: the backbone registry
   covers `core.*`, module-owned codes live in the module's own spec, and `modules.notes.*` appears in
   Appendix A only because `notes` is itself specified in that document (§18).

## Files

- `src/disp/core/errors.py` — `ERROR_CODE_RE`, `validate_error_code`, two call sites.
- 8 further files under `src/` — `core/auth/{acl,dependencies,routes}.py`, `core/{dashboard,pagination,
  settings_store}.py`, `modules/{notes,plants}/service.py`. 59 literals.
- 11 files under `tests/`, 53 assertions. `tests/core/test_errors.py` gains the two guard tests.
- 32 files under `clients/web/`, 65 literals — the four `describe*Error` ladders, the inline
  `problem.code` comparisons in `refresh.ts`/`CompleteDialog`/`IntervalFormDialog`, `problem.ts`'s
  synthesised fallback, the route files, and their tests.
- `TECHNICAL-SPEC.md` (§17.4, Appendix A rewritten with a normative naming section),
  `TECHNICAL-SPEC-WEB.md` (§7.2/§7.3/§8.4/§8.6/§21), `docs/auth.md`, `docs/operations.md`, `CLAUDE.md`
  (new "Error codes are three segments" section), `src/disp/modules/{notes,plants,learning}` docs,
  `milestones/server/{M19,M20}`.

## Verification

- `./dev test` — 190 passed, coverage 88.03 %. The backend suite asserts exact code strings in 11 files,
  so a missed rename fails loudly rather than silently.
- `cd clients/web && pnpm test` — 63 files, 297 tests passed, coverage gates met.
- `./dev lint` — clean apart from three pre-existing `notes/service.py` findings (import order and two
  `%`-format calls in `purge_deleted`) that are present on `prod` and out of scope here.
- Residual grep for every old shape across `src/`, `tests/` and `clients/web/` returns only false
  positives: the tile-key fixture `notes.recent`, the filename `notes.txt`, SQL table names
  (`plants.care_log`), and `settings.<field>` attribute access.
- Manifest keys verified unchanged — `plants.due`, `notes.latest`, `plants.daily_check`,
  `notes.purge_deleted`, `plants.care_due`, `notes.note`, `plants.plant` all still two-segment. This was
  the main hazard of the rename: a pattern-based rewrite would have turned the tile key `notes.latest`
  into `modules.notes.latest` and broken tile resolution with no test necessarily catching it, which is
  why the migration used an explicit 42-entry allow-list rather than a regex over dotted strings.

## Dependencies

None. Touches every layer but depends on nothing new. `M18-files.md` was rewritten against the
post-M21 shape rather than migrating onto it, which is why this landed first.
