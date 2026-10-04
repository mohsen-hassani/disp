# M03 — Authentication in the browser

**Status:** Complete

**Scope:** `clients/web/src/auth/{tokenStore.ts,AuthProvider.tsx,refresh.ts,useAuth.ts,guards.tsx}`,
`clients/web/src/routes/{login.tsx,accept-invite.tsx}`.

Covers TECHNICAL-SPEC-WEB.md §8 (Authentication in the browser) in full — the spec's own
highest-risk section. Also §23.3 test cases 1–14, which define this milestone's acceptance bar.

---

## Why this section is treated as its own milestone

§8 opens: *"This section is normative in its entirety and is the highest-risk part of the client."*
Nothing here is optional or a judgment call for the implementer — every subsection is a hard
requirement, so this milestone reproduces the spec's mechanics closely rather than summarizing, and
should not be merged into a broader "routing" or "shell" milestone where it would be easy to cut a
corner under time pressure.

## §8.1 Token storage

`tokenStore.ts` exposes exactly:

```ts
let accessToken: string | null = null;
let expiresAt: number | null = null;

export function setToken(token: string, expiresInSeconds: number): void
export function getToken(): string | null
export function clearToken(): void
export function isExpiringWithin(ms: number): boolean
```

Module-scoped variables, not React state — the token must not trigger re-renders on its own and
must be readable from `client.ts`'s interceptor (M02) without a hook. **Never** write the access
token, refresh token, or password to `localStorage`, `sessionStorage`, IndexedDB, Cache API, a
JS-set cookie, or the URL. Test case 12 asserts this with an automated check (this milestone's own
test, see Verification).

**Permitted `localStorage` keys — exhaustive, nothing else:**

| Key | Value | Purpose |
|---|---|---|
| `disp.theme` | `"light" \| "dark" \| "system"` | Theme override (M01 already reserved this) |
| `disp.installDismissedAt` | epoch ms | Install-prompt suppression (M09 writes this) |

## §8.2 Auth states

```ts
type AuthState =
  | { status: 'loading' }
  | { status: 'anonymous' }
  | { status: 'authenticated'; user: UserOut }
  | { status: 'revoked'; reason: 'reuse_detected' };
```

`revoked` is distinct from `anonymous` specifically because it must produce a visible security
warning, not a silent redirect — don't collapse these two states to simplify the reducer.

## §8.3 Bootstrap sequence

On mount, `AuthProvider` MUST, in order:

1. Set `loading`. Render a full-page skeleton — never a redirect, never the login screen.
2. `POST /api/auth/refresh` with `X-Requested-With: disp` (M02's corrected value) and
   `credentials: 'same-origin'`.
3. `200` → store the token, schedule proactive refresh (§8.5), call `GET /api/auth/me`, set
   `authenticated`.
4. `401 auth.refresh_token_reused` → set `revoked`.
5. Any other `401`/`403` → set `anonymous`.
6. Network failure: if a cached `GET /api/auth/me` response exists in the query cache **and** the
   app is offline, enter the degraded read-only authenticated state (§18.4 — implemented in M09;
   this milestone's job is to make the *state* reachable, M09 wires the actual offline-cache
   plumbing). Otherwise `anonymous`.

The bootstrap request MUST complete before any authenticated route renders — route loaders (M04)
await it.

## §8.4 Reactive refresh (single-flight) — `refresh.ts`

Exact algorithm, in order:

1. Non-401 response → return unchanged.
2. Failed request was itself `/auth/refresh`, `/auth/login`, `/auth/logout`, or
   `/auth/accept-invite` → do not retry, return the response.
3. Problem `code` is `auth.refresh_token_reused` → hard logout (§8.6), return.
4. Request already retried once (tracked via a symbol on the request init) → return the response.
5. A refresh already in flight → await the existing promise; otherwise start one and store the
   promise so concurrent 401s share it. **At most one in-flight refresh per tab, no exceptions.**
6. Refresh succeeds → replay the original request once with the new token, return that response.
7. Refresh fails → soft logout, return the original `401`.

This is the mechanism test cases 8–10 exist to prove (three concurrent 401s → exactly one refresh
call and all three replayed; a 401 on `/auth/refresh` itself doesn't recurse; an already-retried
request isn't retried again). Write those as this milestone's own tests, don't defer them to M11 —
a subtle bug here (e.g. forgetting to clear the in-flight promise after it resolves) is much cheaper
to catch immediately than after five more milestones are built on top of it.

## §8.5 Proactive refresh

After a successful login or refresh, schedule a timer for `expires_in - 60` seconds (minimum 30s)
that calls refresh. Clear the timer on logout and on `visibilitychange` to hidden; re-evaluate on
`visibilitychange` to visible — if the token is expired or expires within 60s, refresh immediately
before resuming other requests. (A phone asleep for an hour returns with a dead token; refreshing on
wake avoids a burst of 401s — test case 14.)

## §8.6 Logout — three distinct paths

- **Soft** (token simply invalid): clear in-memory token, clear the TanStack Query cache, purge all
  Cache Storage entries whose URL contains `/api/` (coordinate with M09, which owns the service
  worker's cache — this milestone calls the purge, M09 defines what's cached in the first place),
  set `anonymous`, navigate to `/login?next=<current path>`.
- **Explicit** (user clicked Sign out): `POST /api/auth/logout`, then the soft-logout steps, then
  navigate to `/login` with no `next`.
- **Hard** (`auth.refresh_token_reused`): soft-logout steps, set `revoked`, navigate to `/login`,
  render the persistent security banner (dismissed only by explicit user action).

Cache purging on **every** logout path is mandatory — a cached response surviving a reload is
readable by the next person on a shared device.

## §8.7 Login screen (`/login`)

- Fields: email (`type="email"`, `autocomplete="username"`), password (`type="password"`,
  `autocomplete="current-password"`).
- Submit → `POST /api/auth/login`. `200` → store token, invalidate `qk.auth.me()`, navigate to
  `next` **only if** it's a same-origin relative path starting with `/`; otherwise navigate to `/`.
  An absolute or protocol-relative `next` is ignored — this is an open-redirect defense, test case 5.
- `401 auth.invalid_credentials` → one generic form-level error (Appendix D copy). MUST NOT
  distinguish unknown-email from wrong-password (mirrors backend §10.4 — test case 6).
- `403 auth.account_disabled` → distinct form-level copy.
- `429` → disable submit for `Retry-After` seconds with a live countdown (test case 7).
- Submit button disabled + spinner while in flight; double-submit must be impossible.
- No "remember me" — the 30-day refresh cookie is the only persistence. No password-reset link —
  static copy directing to the administrator (backend has no such flow).

## §8.8 Invite acceptance (`/accept-invite`)

Reads `token` from the query string. Fields: display name, password, confirm password. Client-side
policy mirrors backend §10.3 (≥12 chars, ≤128, ≠ the invited email), advisory strength meter. Success
→ server returns a session; store the token, navigate to `/`. Distinct screen states (no form
rendered) for `404 auth.invite_not_found`, `409 auth.invite_used`, `410 auth.invite_expired`, each
with Appendix D copy.

## §8.9 What the client MUST NOT do

- MUST NOT create, read, or store a personal access token for its own use — PATs are CLI-only
  (backend §10.7). The token-*management* UI (list/revoke, M07) never authenticates with one.
- MUST NOT read the refresh cookie (it's `HttpOnly`; JS can't anyway, but don't try).
- MUST NOT decode the access token for claims — identity comes from `GET /api/auth/me` only.

## Dependencies

- **M02** for `client.ts` (interceptor extension point), `problem.ts`, `queryKeys.ts`.
- Blocks **M04** (the `_app` route guard awaits this milestone's bootstrap) and **M07** (account/
  token screens use `useAuth()`).

## Verification — test cases 1–14 (§23.3), implement now rather than deferring all to M11

1. Bootstrap: successful refresh → `authenticated`, login screen never renders.
2. Bootstrap: `401` → `anonymous`, guarded route redirects to `/login?next=…`.
3. Bootstrap: `auth.refresh_token_reused` → `revoked`, security banner renders.
4. Login success stores token, navigates to `next`.
5. Absolute-URL `next` is ignored; navigates to `/`.
6. Login `401` shows one generic error for both failure modes.
7. Login `429` disables submit and counts down.
8. Three concurrent `401`s → exactly one refresh call, all three replayed.
9. A `401` on `/auth/refresh` itself does not recurse.
10. An already-retried-once request is not retried again.
11. Explicit logout calls the endpoint, clears the query cache, purges `/api/` cache entries.
12. **No credential reaches persistent storage** after a full login flow (`localStorage`,
    `sessionStorage`, all Cache Storage entries — check for both the token and the password).
13. Proactive refresh fires at `expires_in - 60s`.
14. Returning to visibility with an expired token refreshes before other requests fire.

Full Playwright e2e coverage of these against a real backend is M11's job; this milestone should at
minimum pass all 14 as Vitest/RTL + MSW component/unit tests before being considered done.

---

## Implementation notes (this milestone is now built)

### No router exists yet — a router-agnostic navigation shim, not a workaround

M04 (routing/shell) hasn't landed, so `src/routes/login.tsx` and `accept-invite.tsx` are plain
exported React components, not `createFileRoute`-wrapped route files — wiring them into
TanStack Router's file-based tree is M04's job. Reading `next`/`token` from
`window.location.search` directly (rather than router-provided typed search params) and
navigating via a new `src/lib/navigate.ts` (a swappable `navigate()`/`setNavigate()` pair,
defaulting to `window.location.assign`) both work correctly today — a full-page reload after
login still lands on a working, authenticated page, since `AuthProvider` re-bootstraps from the
`HttpOnly` refresh cookie on every mount exactly as the first page load would. M04 should call
`setNavigate(router.navigate)` once the router exists, trading the one avoidable round-trip for
client-side navigation; nothing about `login.tsx`/`accept-invite.tsx`'s internal logic needs to
change for that swap. The same shim backs `guards.tsx`'s redirect and `refresh.ts`'s logout paths.

### File layout deviates from the milestone's literal 5-file list — deliberately

The literal scope list names `tokenStore.ts, AuthProvider.tsx, refresh.ts, useAuth.ts, guards.tsx`.
Two small additions were needed to avoid a circular import between `AuthProvider.tsx` (needs
`refresh.ts`'s `scheduleProactiveRefresh` after login) and `refresh.ts` (needs logout side effects
that also live conceptually with "session state"):

- **`src/auth/authState.ts`** (new, ~30 lines): the `AuthState` type plus a plain module-scoped
  external store (`getAuthState`/`setAuthState`/`subscribeAuthState`), consumed via
  `useSyncExternalStore` rather than React Context. This is what lets `refresh.ts` — which runs
  outside any component, registered on `client.ts` at module load — transition auth state (e.g.
  into `revoked` on reuse detection) without depending on React at all. `AuthProvider.tsx` and
  `useAuth.ts` both subscribe to the same store instead of one depending on the other for state.
- **`src/lib/navigate.ts`** (new, ~15 lines): see above — not auth-specific, so it lives beside
  M01's `lib/theme.ts`/`lib/cn.ts` rather than in `auth/`.

With `authState.ts` as the shared, dependency-free primitive, the actual dependency graph is
one-directional: `refresh.ts` depends on `authState.ts` + `tokenStore.ts` + `lib/navigate.ts` only;
`AuthProvider.tsx` depends on `refresh.ts` (for `scheduleProactiveRefresh`/`softLogout`) plus the
same primitives; `useAuth.ts` depends on `AuthProvider.tsx`'s action exports plus `authState.ts`.
Login/explicit-logout/accept-invite actions live as plain exported functions in `AuthProvider.tsx`
itself (not a separate `actions.ts`) since keeping the file list this close to the specified five
seemed worth it once the two real primitives above resolved the actual circularity problem.

### §8.4's step ordering, read literally, could never trigger hard logout — resolved by intent, not letter

§8.4 numbers "check for `auth.refresh_token_reused`" as step 3, *after* step 2's "don't retry
/auth/refresh, /auth/login, /auth/logout, /auth/accept-invite requests." Read as a strict
if-elif chain, step 2 would catch every failure of `/auth/refresh` itself and return before step 3
ever runs — but `auth.refresh_token_reused` is a code *only* the refresh endpoint ever returns
(confirmed against `src/disp/core/auth/routes.py`), so literally that ordering makes step 3
unreachable in practice. The implemented interceptor (`handleUnauthorizedResponse` in
`refresh.ts`) instead treats "reused" as one of two possible **outcomes of step 5's own refresh
attempt** (the other being a generic "failed"), branching to hard-logout vs. soft-logout
accordingly — this is what step 3 and step 7 clearly intend together, just not what a literal
top-to-bottom reading of the numbered list produces. Bootstrap (`AuthProvider.bootstrap`) has its
own, separate, direct handling of the same code on its own `/auth/refresh` call, per §8.3 — it was
never supposed to go through this interceptor's retry logic at all, since bootstrap isn't retrying
anything.

### A redundant-but-harmless extra call, kept because the spec asks for it

The backend's `/api/auth/refresh` and `/api/auth/login` responses both already include the full
`user` object (confirmed: `AuthRefreshResponse`/`AuthLoginResponse` are both the generated
`LoginResponse` type, `user: UserOut` included) — meaning bootstrap's explicit step 3
("call `GET /api/auth/me`") is provably redundant with data already in hand. Implemented it anyway,
exactly as specified: it's cheap, correct, and an explicit MUST, unlike the other deviations above
which were genuine contradictions forcing a choice. `login()`/`acceptInvite()` don't make the
extra call, matching §8.7/§8.8's text, which — unlike §8.3 — never asks for one.

### One rule from §8.8 is not client-checkable at all

"Password ≠ the invited email" (mirroring backend §10.3) can't be enforced in
`accept-invite.tsx`: the invited email isn't known to an unauthenticated client before submission
— there's no "look up an invite by token" endpoint, by design. Client-side validation covers the
length bounds (12–128, confirmed against `src/disp/core/auth/passwords.py`) and the
confirm-password match; the email-equality rule surfaces only via the server's
`422 auth.password_policy` response, mapped to the password field like any other server-side
validation failure. Documented in the file itself so a future pass doesn't "fix" this as a bug.

### Extension points left for later milestones, mirroring M02's pattern

- `refresh.setQueryCacheClearer(fn)` — a no-op until M04's QueryClient exists to actually clear
  (§8.6's "clear the TanStack Query cache" logout step).
- `AuthProvider`'s `getCachedUser` prop — the §8.3-step-6/§18.4 offline-degraded-mode hook M09
  wires a real query-cache lookup into; today it's simply never provided, so that branch always
  falls through to `anonymous`, which is the spec's own documented fallback.

### Verification actually performed

- `pnpm typecheck`, `pnpm lint` (ESLint incl. `eslint-plugin-jsx-a11y` on the two forms, Prettier)
  all pass clean.
- `pnpm test`: 34 tests across 9 files, all passing — the 14 required cases plus a few extra
  (guards.tsx's `RequireAuth`/`RequireAdmin`, a couple of accept-invite smoke tests not in the
  required list but cheap insurance for a screen that otherwise had zero coverage).
  `src/auth/` sits at ~84–94% line coverage per file; M11 owns tightening this to the spec's ≥95%
  gate once the full suite (and the remaining milestones' code) exists.
- `pnpm build` succeeds. Notably the production bundle size is **unchanged from M02** — none of
  this milestone's code is reachable from `main.tsx` yet (still M01's trivial stub), so nothing new
  is actually bundled into the shipped app until M04 wires `AuthProvider` and the two screens into
  a real router and entry point. Confirmed clean type-checking and passing tests are what this
  milestone can prove on its own; end-to-end behavior against a running app is M04's to prove.
