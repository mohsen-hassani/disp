# M02 — Generated API client and HTTP layer

**Status:** Complete

**Scope:** `clients/web/openapi-ts.config.ts`, `clients/web/src/api/{generated/,client.ts,problem.ts,
queryKeys.ts}`.

Covers TECHNICAL-SPEC-WEB.md §6 (API client generation), §7 (HTTP layer and error mapping),
Appendix A (query key registry).

---

## §6. API client generation

`openapi-ts.config.ts` MUST be exactly:

```ts
import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: '../../openapi.json',
  output: { path: 'src/api/generated', format: 'prettier', lint: 'eslint' },
  plugins: [
    '@hey-api/client-fetch',
    '@hey-api/typescript',
    '@hey-api/sdk',
    '@tanstack/react-query',
  ],
});
```

`../../openapi.json` is produced by the backend's `./dev openapi` (already exists —
`./dev:28,106-113`, confirmed working against the current backend). Run it once, from the repo
root, before `pnpm api:generate` in `clients/web/`.

Rules, all normative:

- Generated output under `src/api/generated/` MUST be committed — a clean checkout must build with
  no backend running (§25 acceptance criterion 1).
- Generated files are read-only from the implementer's side. ESLint ignores the directory (M01
  already configured this); TypeScript still type-checks it.
- Every request/response type used anywhere in the app comes from `types.gen.ts`. No hand-written
  interface may mirror an API shape.
- `pnpm api:check` (M01's script) regenerates and fails the build if the tree goes dirty — this is
  what proves the committed client matches `openapi.json` (§25 criterion 2). Wire this into CI in
  M12, but the script itself is created here.
- Operation IDs are already stable and explicit in the backend for every route this milestone
  touches (`dashboard_manifest`, `dashboard_tiles`, `dashboard_tile`, `settings_get`,
  `settings_update`, `notes_list`, `notes_create`, etc. — verified directly in
  `src/disp/core/dashboard.py`, `settings_store.py`, `src/disp/modules/notes/router.py`, and
  `auth_refresh` in `src/disp/core/auth/routes.py`). Generated SDK method names will therefore be
  stable across regeneration; a name changing on a future `api:generate` run is a real API change to
  review, not something to silently accept.

**Depends on M00 having landed** for `SettingsPanelOut.schema`/`x-secret` to appear in
`openapi.json` at all — regenerate against the amended backend, not the pre-M00 one, or M06 will
have no `schema` field to consume later. The other endpoints this milestone's `client.ts`/error
plumbing needs (auth, dashboard tiles, notes) are unaffected by M00 and work against today's backend.

## §7. HTTP layer and error mapping

### `src/api/client.ts`

Configure the generated fetch client with:

- `baseUrl: '/api'`
- `credentials: 'same-origin'`
- Request interceptor: add `Authorization: Bearer <token>` when M03's token store holds one;
  **omit the header entirely** otherwise (never send `Authorization: Bearer null` or similar).
- Request interceptor: add `X-Requested-With: disp` to `POST /auth/refresh` and
  `POST /auth/logout` only. **Use `disp``** — see M00's
  "spec-vs-reality correction" section; the backend's `_require_csrf_header()`
  (`src/disp/core/auth/routes.py:79`) rejects anything else.
- Response interceptor implementing the 401 refresh flow — the actual single-flight state machine
  is M03's `refresh.ts`; this milestone wires the interceptor's call site into it but the logic
  itself (in-flight promise sharing, retry-once tracking, hard-logout branch) is M03's scope. Don't
  duplicate that state machine here.
- Default timeout: `AbortSignal.timeout(15_000)`.

### `src/api/problem.ts`

```ts
export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  code: string;
  request_id: string;
  errors?: Array<{ loc: (string | number)[]; msg: string; type: string }>;
}

export function parseProblem(res: Response, body: unknown): ProblemDetail
export function isProblem(value: unknown): value is ProblemDetail
```

`parseProblem` MUST tolerate a non-conforming body (HTML error page from a proxy, empty body) and
synthesize `{ code: 'internal_error', ... }` rather than throwing. This matters in practice: a
misconfigured Traefik route or an nginx 502 page is exactly the kind of response this needs to
survive without crashing the error-handling path itself.

### Error presentation rules (§7.3 table — reproduced here as the normative source for M03–M10)

| Server `code` | Client behaviour |
|---|---|
| `auth.refresh_token_reused` | Hard logout. Persistent red banner (Appendix D copy). |
| any other `401` | Attempt refresh once; if that fails, soft logout, redirect to `/login?next=<path>` |
| `403 acl.forbidden` | Inline error on the affected control; toast "You don't have permission to do that." |
| `403 auth.admin_required` | Route guard should have prevented it; render the 403 screen |
| `404` | Route-level: 404 screen. Item-level: toast + invalidate the containing list query |
| `409` | Inline field error where implicated; otherwise toast |
| `410 auth.invite_expired` | Dedicated screen state on `/accept-invite` |
| `422` | Map `errors[].loc` to form fields (§19.3, detailed in M10); unmapped → form-level error |
| `429` | Toast with `Retry-After` as "Try again in N seconds"; disable submit for that duration |
| `5xx` | Toast "Something went wrong on the server." plus copyable `request_id` |
| Network failure | `navigator.onLine === false` → offline copy; otherwise generic network copy |

The client MUST NOT display the raw `detail` string for `5xx` (defense in depth — don't rely on the
backend's guarantee that it's generic). `4xx` `detail` strings are safe and preferred over generic
copy. `request_id` MUST surface on every `5xx` toast — it's the only thread between a user report and
a server log line.

This milestone builds the *plumbing* (`problem.ts`, the interceptor skeleton, the table above as
documented reference); wiring specific codes into specific screens (login errors, share-dialog field
errors, etc.) happens in each screen's own milestone (M03, M06–M08).

### `src/api/queryKeys.ts` — Appendix A, verbatim

```ts
export const qk = {
  auth: {
    me:      () => ['auth', 'me'] as const,
    tokens:  () => ['auth', 'tokens'] as const,
    invites: () => ['auth', 'invites'] as const,
  },
  dashboard: {
    manifest: () => ['dashboard', 'manifest'] as const,
    tiles:    () => ['dashboard', 'tiles'] as const,
    tile:     (key: string) => ['dashboard', 'tile', key] as const,
  },
  settings: {
    domain: (domain: string) => ['settings', domain] as const,
  },
  notes: {
    all:    () => ['notes'] as const,
    list:   (f: { q?: string; pinned?: boolean }) => ['notes', 'list', f] as const,
    detail: (id: string) => ['notes', 'detail', id] as const,
  },
} as const;
```

No ad-hoc query-key literal is permitted anywhere else in the app — every `useQuery`/`useMutation`
in every later milestone imports from here. The QueryClient defaults (staleTime/gcTime/retry
policy, §10.1) and the per-query/invalidation tables (§10.2–10.3) are **M04's and each feature
milestone's** concern to apply at the call site; this file only defines the keys.


## Dependencies

- **M00** must have landed for `openapi.json` to include `SettingsPanelOut.schema`/`x-secret`
  (needed later by M06; this milestone's own scope doesn't require it, but regenerate against
  post-M00 backend so M06 doesn't need a second regeneration pass).
- **M01** for the `clients/web/` tree, `tsconfig`, and the `api:generate`/`api:check` scripts to
  exist.

## Open questions / judgment calls for the implementer

- Where exactly the 401-interceptor's call-out to M03's refresh logic lives (a callback registered
  by `AuthProvider` at mount vs. a direct import of `refresh.ts` from `client.ts`) is left to M03 to
  decide — this milestone should leave an obvious extension point (e.g. an exported
  `setUnauthorizedHandler(fn)`) rather than guessing M03's internal shape.

## Verification

- `pnpm api:generate` runs cleanly against a running dev backend's `openapi.json`; commit the
  output.
- `pnpm api:check` passes (no diff) on a second run with no backend changes.
- Unit test (Vitest, per M11's layer but reasonable to write now): `parseProblem` against a
  malformed/empty body does not throw and returns `code: 'internal_error'`.
- Unit test: a request to a non-auth endpoint carries no `X-Requested-With` header; a request to
  `/auth/refresh` carries `X-Requested-With: disp` exactly.

---

## Implementation notes (this milestone is now built)

`@hey-api/openapi-ts` is at `0.99.0` (M01 pinned it against current registry versions, far past
the spec's `>=0.64` floor written against an older release), and its output shape has moved on
from what §5/§6 describe. Three real deviations found and resolved:

### 1. The generated client is now fully self-contained — `@hey-api/client-fetch` is dead weight

§5's tree lists three generated files (`types.gen.ts`, `sdk.gen.ts`,
`@tanstack/react-query.gen.ts`) importing a separate `@hey-api/client-fetch` runtime package. At
`0.99.0`, `output.path` instead produces 17 files across `client/`, `core/`, and the three
top-level ones, with the fetch-based client runtime bundled directly into `client/client.gen.ts` —
confirmed with `grep -r '@hey-api/client-fetch' src/api/generated/` returning nothing. This matches
the deprecation notice M01 already flagged ("Starting with v0.73.0, this package is bundled
directly inside @hey-api/openapi-ts"). The standalone `@hey-api/client-fetch` dependency M01 added
per §4's literal table has been **removed from `package.json`** — it installs fine but nothing
imports it, and M01's own note asked M02 to check exactly this.

### 2. `output.lint: 'eslint'` directly contradicts §6.2's own ESLint-ignore requirement

Running the spec's literal `openapi-ts.config.ts` failed outright: `output.lint: 'eslint'` makes
codegen invoke `eslint src/api/generated` as a post-processing step, but `eslint.config.js`
(correctly, per §6.2: "ESLint MUST ignore that directory") has that exact path in its `ignores`.
Under ESLint 9+, explicitly targeting an ignored path is a **hard error** ("all matching files are
ignored"), not the silent no-op older ESLint versions used to treat it as. §6.1 and §6.2 are in
direct tension here, and §6.2's normative "MUST ignore" wins: `output.lint`/`output.format` are
replaced with `output.postProcess: ['prettier']` (dropping `'eslint'`), matching the tool's own
deprecation guidance for both keys and giving generated code consistent formatting without fighting
the ignore rule. (One more wrinkle: the runtime deprecation message reads `postProcess: [...]` as
if it were a top-level config key, but the actual published type only accepts it nested under
`output` — confirmed by reading `@hey-api/openapi-ts`'s shipped `.d.mts`. Placing it top-level
fails typecheck; nesting it under `output` is what actually type-checks and runs.)

### 3. `baseUrl: '/api'` would double-prefix or mis-prefix real routes — use `''`

§7.1 says to configure `baseUrl: '/api'`, which assumes every operation path in the generated SDK
is relative (e.g. `/auth/refresh`). This backend's actual `openapi.json` already emits each
operation's **full absolute path exactly as mounted** — `/api/auth/refresh`, `/api/notes`,
`/api/settings/{domain}`, but plain `/health` and `/health/live` with **no** `/api` prefix
(confirmed by listing `openapi.json`'s `paths` directly). Configuring `baseUrl: '/api'` would have
produced `/api/api/auth/refresh` for every API call and incorrectly prefixed the two health routes
to `/api/health...`. `src/api/client.ts` uses `baseUrl: ''` instead — each operation's own absolute
path resolves against the current origin, which is exactly what §2.1's same-origin/relative-URL
requirement wants, just without an extra prefix layered on top.

### Extension points for M03, as anticipated

`setAccessTokenGetter(getter)` and `setUnauthorizedHandler(handler)` are exported from
`client.ts`, exactly the shape the milestone's "open questions" section anticipated. Until M03
registers them: no token is ever attached (safe default), and a 401 passes through completely
unhandled (no silent swallowing, no crash) — verified in `tests/unit/api/client.test.ts`.

### Testing note: Node's native `Request` needs an absolute URL, unlike a real browser

`tests/unit/api/client.test.ts` overrides `client`'s `baseUrl` to `http://localhost` for the
duration of that file only. Under Vitest + jsdom, the global `fetch`/`Request` are Node's native
(undici) implementations — jsdom itself ships no fetch/Request of its own — and undici's `Request`
constructor throws `Failed to parse URL from /health/live` for a relative URL, because unlike a
real browser it has no document location to resolve against. This is purely a test-environment
artifact (confirmed by tracing a swallowed error through the generated client's `throwOnError:
false` default, which silently returns `{ error }` instead of surfacing the `TypeError` — a good
reminder to inspect `result.error instanceof Error` rather than trust a resolved promise means
success). Production behavior is unaffected: real browsers resolve relative URLs against
`document.location` exactly as §2.1 assumes.

### Verification actually performed

- `./dev openapi` (backend) → `pnpm api:generate` → 17 files under `src/api/generated/`, committed.
- `pnpm api:check` passes with the generated output staged (no diff on regeneration).
- `pnpm typecheck`, `pnpm lint`, `pnpm build`, `pnpm test` (9 tests: 5 for `problem.ts`, 4 for
  `client.ts`'s header/timeout/401-passthrough behavior) all pass.
- Confirmed directly in `types.gen.ts` that `SettingsPanelOut.schema` (M00's A1) is present and
  required, proving the amendment flows all the way through codegen to a usable TS type.
