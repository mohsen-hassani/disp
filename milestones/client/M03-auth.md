# M03 — Authentication in the browser

**Status:** Not started

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

(Renamed from the spec's literal `mystuff.theme`/`mystuff.installDismissedAt` — see DISP naming
section below.) No user id, no email, no route history, ever.

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

## DISP naming applied here

- `disp.theme` / `disp.installDismissedAt` (not `mystuff.*`) — enforced by this milestone's own
  no-persisted-credential test, which should also assert no `mystuff.*` key exists.
- `X-Requested-With: disp` on refresh/logout (inherited from M02's corrected client config; this
  milestone's bootstrap/login/logout calls must actually use that configured client, not bypass it).
- Page titles: `Sign in · DISP`, `Accept invitation · DISP` (finalized by M04's route table, but the
  string constants belong to this milestone's route files).

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
