# M06 — Generic settings rendering

**Status:** Not started

**Scope:** `clients/web/src/routes/{_app.settings.index.tsx,_app.settings.$domain.tsx}`,
`clients/web/src/components/schema-form/{SchemaForm.tsx,fieldFor.tsx,schemaToZod.ts,
widgets/{String,Number,Boolean,Enum,Array,Object,Secret}.tsx}`.

Covers TECHNICAL-SPEC-WEB.md §14 (Generic settings rendering) in full, Appendix B (JSON Schema to
widget mapping).

**Hard dependency: this milestone cannot be built end-to-end against a real backend until
[[M00-backbone-amendments]] lands.** Component-level work (widget rendering, `schemaToZod`,
secret-field UI) can proceed against a hand-written fixture schema, but do not consider this
milestone done until it's been verified against a live `GET /api/dashboard/manifest` response
carrying a real `schema` field with a real `x-secret` marker.

---

## §14.1 Data flow

1. `qk.dashboard.manifest()` provides each module's settings panels, each with `key`, `title`,
   `description`, `scope`, and — once M00 lands — `schema` (JSON Schema).
2. `GET /api/settings/{domain}` (`qk.settings.domain(domain)`) → current values, secrets masked as
   `"***"`.
3. `PUT /api/settings/{domain}` saves. **Only changed keys are sent** — this is not an optimization,
   it's required so an untouched secret field's `"***"` sentinel is never round-tripped (§14.4).

`/settings` (index) lists every panel across all modules, grouped by module, plus the fixed Account
and API tokens entries (M07 owns those two screens; this route just links to them).
`/settings/:domain` renders that module's panels.

## §14.2 Why not a library — do not reach for one under time pressure

`@rjsf/core` is forbidden: >100KB, imposes its own theming, and produces markup that fails §21
without extensive overrides. The JSON Schema subset the backend emits is small and fully enumerated
in Appendix B — a purpose-built renderer of roughly 300 lines is smaller, more accessible, and more
predictable than fighting a general-purpose library's defaults. If this milestone's widget set is
tempted to grow past what Appendix B enumerates, that's a signal the backend is emitting something
unexpected — check M00's amendment first, don't expand the renderer to cover it silently.

## §14.3 `SchemaForm`

Accepts a JSON Schema, an initial value, and `onSubmit`. MUST:

1. Convert the schema to a Zod schema via `schemaToZod.ts` for client-side validation.
2. Render fields via `fieldFor.tsx`, dispatching on `type`, `format`, `enum`, and `x-secret`.
3. Use `title` for the label, `description` for help text, `default` for the initial value when the
   current value is absent.
4. Mark `required` fields, set `aria-required`.
5. **An unsupported schema construct renders as a disabled field** with "This setting can't be
   edited here." — never crash, never silently drop it. Forward compatibility matters: a future
   module may emit a construct this client predates, and silently dropping a field would look like
   data loss to the user even though nothing was actually lost server-side.
6. Track dirty state per field; send only changed keys on submit.
7. Warn on navigation away with unsaved changes, via the router's `blocker`.

## §14.4 Secret fields

A property with `"x-secret": true` (produced by M00's amendment):

- Renders `type="password"`, `autocomplete="off"`.
- Current value `"***"` → render empty, placeholder "Saved — leave blank to keep", muted "Set"
  badge.
- Current value `null` → render empty, "Not set" badge.
- **Untouched secret field is omitted from the payload entirely on submit** — never send the
  literal `"***"` back even though the backend tolerates it; omission is unambiguous, echoing
  `"***"` is not.
- A "Clear" button next to a set secret sends `null` for that key.
- Secret values MUST NOT be logged, placed in error messages, or included in any toast, anywhere in
  the app — this constraint outlives this milestone; keep it in mind if a later milestone's error
  handling is tempted to interpolate a field value into a message.

## Appendix B — widget mapping (exhaustive; this table is the whole spec for `fieldFor.tsx`)

| Schema | Widget | Zod |
|---|---|---|
| `{"type":"string"}` | Single-line text input | `z.string()` |
| `{"type":"string","format":"email"}` | `type="email"` input | `z.string().email()` |
| `{"type":"string","format":"uri"}` | `type="url"` input | `z.string().url()` |
| `{"type":"string","format":"date-time"}` | `type="datetime-local"` input | `z.string().datetime()` |
| `{"type":"string","maxLength":>200}` | Textarea, 4 rows | `z.string().max(n)` |
| `{"type":"string","x-secret":true}` | Secret field (§14.4) | `z.string().optional()` |
| `{"type":"string","enum":[…]}` | Select; radio group when ≤3 options | `z.enum([…])` |
| `{"type":"integer"}` | `type="number"`, `step=1` | `z.number().int()` |
| `{"type":"number"}` | `type="number"`, `step=any` | `z.number()` |
| `{"type":"boolean"}` | Switch | `z.boolean()` |
| `{"type":"array","items":{"type":"string"}}` | Repeatable text rows, Add/Remove | `z.array(z.string())` |
| `{"type":"array","items":{"type":"object"}}` | Repeatable field group, Add/Remove | `z.array(z.object({…}))` |
| `{"type":"object","properties":{…}}` | Nested fieldset with legend | `z.object({…})` |
| `{"anyOf":[X,{"type":"null"}]}` | Widget for X, marked optional | `X.nullable()` |
| `{"$ref":"#/$defs/X"}` | Resolve and recurse | resolved |
| anything else | Disabled fallback field | `z.unknown()` |

Constraints honored: `minLength`, `maxLength`, `pattern`, `minimum`, `maximum`, `minItems`,
`maxItems`, `required`, `default`, `title`, `description`. Nesting deeper than 3 levels renders the
fallback — the backend isn't expected to emit it, so don't build recursive handling past that depth
speculatively.

## §14.5 Save behavior

No optimistic updates here (unlike the three permitted exceptions in §10.4 — settings saves are not
one of them). Form disables during the request, submit button shows a spinner, success → toast +
dirty-state reset to the server's response. `422` maps to field errors per M10's §19.3 algorithm.
`500 settings.decryption_failed` shows the distinct Appendix D copy ("the server's encryption key may
have changed") — this is a real operational signal the user needs to escalate, not a generic retry-
able error, so don't route it through the generic 5xx toast.

## Dependencies

- **M00** — hard dependency, see above.
- **M02** — generated client, query keys.
- **M04** — `/settings` and `/settings/:domain` render inside `_app`.
- Feeds **M05**'s `TileActionDialog` (reuses `SchemaForm` for `body_schema`-driven action dialogs)
  and **M07** (Account/Tokens/Invites screens are hand-built, not schema-driven, but should reuse
  this milestone's dirty-tracking/save-state patterns for consistency).

## Open questions / judgment calls for the implementer

- Whether `$ref` resolution assumes `$defs` are always inlined at the top level of the panel's own
  schema (per M00's A1 note that Pydantic keeps `$defs` local) or whether `fieldFor.tsx` should walk
  an arbitrary document tree looking for definitions elsewhere. Assume the former — M00 asserts this
  with a test — and treat a `$ref` that doesn't resolve locally as the "anything else" fallback
  case, not a crash.
- How deep the "3 levels" nesting limit in Appendix B is counted from (the panel root, or from each
  `$ref` resolution point) isn't specified. Count from the panel root — simplest, and the backend
  isn't expected to test this boundary today per the same note.

## Verification

- Test cases 28–34 (§23.3): each widget type renders correctly; `required` fields block submit when
  empty; an unsupported construct renders disabled without crashing; a `"***"` secret round-trips
  without ever sending the literal back; Clear sends `null`; only changed keys appear in the `PUT`
  payload; `422` errors map to the right fields.
- Manual, post-M00: load `/settings/core.notifier` (or whichever panel exists) against a live dev
  backend and confirm the `urls` secret field shows the "Saved" badge, and that toggling Clear then
  saving actually sends `{"urls": null}` — inspect the network request, don't just trust the UI.
