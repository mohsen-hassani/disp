# MyStuff Web Client — Technical Specification

**Document type:** Implementation specification
**Version:** 1.0
**Status:** Approved for implementation
**Scope:** The responsive, installable Progressive Web App that consumes the MyStuff HTTP API
**Companion document:** *MyStuff Platform — Technical Specification v1.0* (referred to below as **PLATFORM-SPEC**)

---

## How to read this document

This specification is **normative and complete**. An implementing agent must not invent behaviour that is not described here. Keywords follow RFC 2119: **MUST**, **MUST NOT**, **SHOULD**, **MAY**.

Every reference of the form "PLATFORM-SPEC §10.5" points at the backend specification. Where this document and PLATFORM-SPEC disagree, PLATFORM-SPEC wins and the implementer **MUST** stop and report the conflict.

Section 3 lists three small amendments this client requires from the backend. Those amendments **MUST** be implemented before the corresponding client features.

---

## Table of Contents

1. [Goals and non-goals](#1-goals-and-non-goals)
2. [Load-bearing decisions](#2-load-bearing-decisions)
3. [Required backbone amendments](#3-required-backbone-amendments)
4. [Technology stack](#4-technology-stack)
5. [Repository layout](#5-repository-layout)
6. [API client generation](#6-api-client-generation)
7. [HTTP layer and error mapping](#7-http-layer-and-error-mapping)
8. [Authentication in the browser](#8-authentication-in-the-browser)
9. [Routing](#9-routing)
10. [Server state management](#10-server-state-management)
11. [Design system](#11-design-system)
12. [Application shell and navigation](#12-application-shell-and-navigation)
13. [Dashboard and generic tile rendering](#13-dashboard-and-generic-tile-rendering)
14. [Generic settings rendering](#14-generic-settings-rendering)
15. [Account, tokens, and admin screens](#15-account-tokens-and-admin-screens)
16. [Notes screens](#16-notes-screens)
17. [PWA behaviour](#17-pwa-behaviour)
18. [Offline strategy](#18-offline-strategy)
19. [Forms and validation](#19-forms-and-validation)
20. [Feedback, errors, and empty states](#20-feedback-errors-and-empty-states)
21. [Accessibility](#21-accessibility)
22. [Performance budgets](#22-performance-budgets)
23. [Testing requirements](#23-testing-requirements)
24. [Build, configuration, and deployment](#24-build-configuration-and-deployment)
25. [Acceptance criteria](#25-acceptance-criteria)
26. [Out of scope](#26-out-of-scope)
27. [Appendix A — Query key registry](#appendix-a--query-key-registry)
28. [Appendix B — JSON Schema to widget mapping](#appendix-b--json-schema-to-widget-mapping)
29. [Appendix C — Design tokens](#appendix-c--design-tokens)
30. [Appendix D — Copy strings](#appendix-d--copy-strings)

---

## 1. Goals and non-goals

### 1.1 Goals

| # | Goal |
|---|---|
| W1 | One responsive codebase serving desktop and mobile; installable as a PWA on Android, iOS, and desktop Chromium. |
| W2 | Render dashboard tiles **generically** from server-supplied `TileData`, with zero client code per module. |
| W3 | Render settings panels **generically** from server-supplied JSON Schema, with zero client code per module. |
| W4 | Cookie + in-memory-access-token authentication with transparent refresh, never persisting a credential to disk. |
| W5 | Full CRUD for the `notes` module, proving that a module can also ship a bespoke screen when a tile is not enough. |
| W6 | Usable read-only when offline; honest and non-destructive when a mutation cannot reach the server. |
| W7 | Every network call typed, generated from `openapi.json` — no hand-written request shapes. |

### 1.2 Non-goals

Do **not** implement: web push notifications; background sync or an offline mutation queue; a service-worker-based offline write cache; screens for plants, habits, or shopping lists; internationalisation beyond locale-aware date/number formatting; theming beyond light/dark; server-side rendering; native app packaging (Capacitor, Tauri); analytics or telemetry of any kind.

### 1.3 Operating assumptions

- One to twenty users, all authenticated. There is no public/anonymous content beyond `/login` and `/accept-invite`.
- The client and the API are served from the **same origin** (§2.1).
- Target browsers: last two major versions of Chrome, Edge, Firefox, and Safari, plus iOS Safari 17+. No Internet Explorer, no legacy Edge.
- Primary device split is roughly even between a desktop browser and a phone home-screen install.

---

## 2. Load-bearing decisions

These four decisions constrain everything else and **MUST NOT** be revisited by the implementer.

### 2.1 Same-origin deployment

The PWA is served from `https://<host>/` and the API from `https://<host>/api`. Traefik routes by path prefix (§24.4).

Consequences, all of them deliberate:
- **No CORS.** `MYSTUFF_CORS_ORIGINS` remains empty. The client MUST use relative URLs (`/api/...`) and MUST NOT accept an API base URL from configuration.
- The refresh cookie (`Path=/api/auth`, `SameSite=Lax`) is transmitted correctly without `SameSite=None`, and is never sent on non-auth API calls.
- There is no runtime configuration to manage, no `config.json` fetch, no `VITE_API_URL`.

### 2.2 Client-side SPA, not server-rendered HTML

PLATFORM-SPEC delivers a pure JSON API (§17) and explicitly forbids the backend from serving a web UI (§26). The client is therefore a static-asset SPA that consumes JSON. HTMX or any other server-rendered approach would require HTML-returning endpoints the backend spec does not have and forbids adding.

### 2.3 React, not Svelte or Vue

Chosen for: first-class OpenAPI codegen with generated TanStack Query options; the largest body of accessible headless-component prior art (Radix); and the highest likelihood of correct output from a coding agent. The generic-rendering requirements (W2, W3) are the bulk of the work here, and they are framework-agnostic — the ecosystem depth matters more than the framework's elegance.

### 2.4 Access tokens live in memory only

No credential is written to `localStorage`, `sessionStorage`, IndexedDB, or the Cache API. The access token exists in a module-scoped variable and React context; it dies with the tab. Session continuity comes from the `HttpOnly` refresh cookie, which JavaScript cannot read. This is the single most important security property of this client (§8).

---

## 3. Required backbone amendments

The following changes to the backend are prerequisites. Each is small and additive.

### A1 — Serialise settings panel schemas (blocking for §14)

PLATFORM-SPEC §8.1 defines `SettingsPanelSpec.schema_model` as a Pydantic class, which is not JSON-serialisable, and §16.1's manifest example shows an empty `settings_panels` array. The dashboard manifest **MUST** serialise each panel as:

```json
{
  "key": "core.notifier",
  "title": "Notification channels",
  "description": "Where notifications are delivered",
  "scope": "user",
  "schema": { "…JSON Schema produced by schema_model.model_json_schema()…" }
}
```

The `schema` field MUST use `mode="serialization"` and MUST inline `$defs` references or keep them resolvable within the same document.

### A2 — Expose secret-field metadata (blocking for §14.3)

PLATFORM-SPEC §14.3 masks secret settings values as the literal string `"***"` and treats `"***"` on write as "leave unchanged". The client cannot infer which fields those are from JSON Schema alone. Each secret property in the emitted schema **MUST** carry `"x-secret": true`.

### A3 — Return the note count on list responses (non-blocking, §16.2)

Optional. If `GET /api/notes` gains a `total` field the client will display it; absent it, the client displays no count. The implementer MUST NOT add this to the backend unilaterally — build the client to work without it.

---

## 4. Technology stack

All versions are **minimum** versions. The implementer MUST pin exact versions in `package.json` and MUST commit `pnpm-lock.yaml`.

| Concern | Package | Constraint |
|---|---|---|
| Runtime | Node.js | `>=22.11 <23` (LTS) |
| Package manager | `pnpm` | `>=9.12` |
| Framework | `react`, `react-dom` | `>=19.0` |
| Build tool | `vite` | `>=6.0` |
| Language | `typescript` | `>=5.6` |
| Routing | `@tanstack/react-router` | `>=1.87` |
| Server state | `@tanstack/react-query` | `>=5.62` |
| API codegen | `@hey-api/openapi-ts` | `>=0.64` |
| HTTP client | `@hey-api/client-fetch` | `>=0.6` |
| Styling | `tailwindcss` | `>=4.0` |
| Headless UI | `@radix-ui/react-dialog`, `-dropdown-menu`, `-checkbox`, `-switch`, `-tabs`, `-toast`, `-tooltip`, `-label` | latest |
| Icons | `lucide-react` | `>=0.460` |
| Forms | `react-hook-form` | `>=7.53` |
| Validation | `zod` | `>=3.23` |
| Schema→form bridge | `@rjsf/core` **is forbidden** — see §14.2 | — |
| Service worker | `vite-plugin-pwa` | `>=0.21` |
| Date formatting | native `Intl` | — |
| Unit tests | `vitest` | `>=2.1` |
| Component tests | `@testing-library/react`, `@testing-library/user-event` | latest |
| API mocking | `msw` | `>=2.6` |
| E2E | `@playwright/test` | `>=1.49` |
| Lint | `eslint` + `typescript-eslint` + `eslint-plugin-jsx-a11y` | latest |
| Format | `prettier` | `>=3.3` |

**Explicitly forbidden:** Redux, MobX, Zustand for *server* state (TanStack Query owns it; a small React context is permitted for auth and theme only); `axios`; `moment`; `date-fns` (use `Intl`); any CSS-in-JS runtime; any component library that ships its own design opinions (MUI, Chakra, Ant); `@rjsf/core`.

---

## 5. Repository layout

The client lives in `clients/web/` of the existing repository. The implementer MUST create exactly this tree.

```
clients/web/
├── package.json
├── pnpm-lock.yaml                          (generated)
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── tailwind.config.ts
├── eslint.config.js
├── .prettierrc
├── playwright.config.ts
├── vitest.config.ts
├── index.html
├── openapi-ts.config.ts
├── public/
│   ├── icons/
│   │   ├── icon-192.png
│   │   ├── icon-512.png
│   │   ├── icon-maskable-192.png
│   │   ├── icon-maskable-512.png
│   │   └── apple-touch-icon.png            (180×180)
│   ├── favicon.svg
│   └── offline.html
└── src/
    ├── main.tsx                            (bootstrap, providers, router)
    ├── routeTree.gen.ts                    (generated by TanStack Router)
    ├── vite-env.d.ts
    ├── api/
    │   ├── generated/                      (generated; committed)
    │   │   ├── types.gen.ts
    │   │   ├── sdk.gen.ts
    │   │   └── @tanstack/react-query.gen.ts
    │   ├── client.ts                       (fetch client config, interceptors)
    │   ├── problem.ts                      (ProblemDetail type + parser)
    │   └── queryKeys.ts                    (Appendix A)
    ├── auth/
    │   ├── AuthProvider.tsx
    │   ├── tokenStore.ts                   (in-memory only)
    │   ├── refresh.ts                      (single-flight refresh)
    │   ├── useAuth.ts
    │   └── guards.tsx                      (requireAuth, requireAdmin)
    ├── routes/
    │   ├── __root.tsx
    │   ├── login.tsx
    │   ├── accept-invite.tsx
    │   ├── _app.tsx                        (authenticated layout)
    │   ├── _app.index.tsx                  (dashboard)
    │   ├── _app.notes.index.tsx
    │   ├── _app.notes.$noteId.tsx
    │   ├── _app.settings.index.tsx
    │   ├── _app.settings.$domain.tsx
    │   ├── _app.settings.account.tsx
    │   ├── _app.settings.tokens.tsx
    │   ├── _app.admin.invites.tsx
    │   └── $404.tsx
    ├── components/
    │   ├── ui/                             (primitives: Button, Input, Dialog, …)
    │   ├── layout/                          (AppShell, SideNav, BottomNav, TopBar)
    │   ├── tiles/
    │   │   ├── TileGrid.tsx
    │   │   ├── TileCard.tsx
    │   │   ├── TileItemRow.tsx
    │   │   ├── TileActionButton.tsx
    │   │   ├── TileActionDialog.tsx
    │   │   ├── TileSkeleton.tsx
    │   │   └── TileError.tsx
    │   ├── schema-form/
    │   │   ├── SchemaForm.tsx
    │   │   ├── fieldFor.tsx                (schema → widget dispatch)
    │   │   ├── widgets/                    (String, Number, Boolean, Enum, Array, Object, Secret)
    │   │   └── schemaToZod.ts
    │   ├── feedback/
    │   │   ├── ToastProvider.tsx
    │   │   ├── ErrorBoundary.tsx
    │   │   ├── EmptyState.tsx
    │   │   └── OfflineBanner.tsx
    │   └── notes/
    │       ├── NoteList.tsx
    │       ├── NoteCard.tsx
    │       ├── NoteEditor.tsx
    │       └── ShareDialog.tsx
    ├── hooks/
    │   ├── useOnlineStatus.ts
    │   ├── useMediaQuery.ts
    │   ├── useIntervalRefresh.ts
    │   └── useInstallPrompt.ts
    ├── lib/
    │   ├── format.ts                       (Intl wrappers: relativeTime, dateTime)
    │   ├── cn.ts                           (class merge)
    │   └── theme.ts
    ├── pwa/
    │   ├── registerSW.ts
    │   └── UpdatePrompt.tsx
    └── styles/
        └── index.css                       (Tailwind v4 + design tokens)

tests/
├── unit/                                   (Vitest + RTL, colocated mocks via MSW)
├── mocks/
│   ├── handlers.ts
│   └── server.ts
└── e2e/
    ├── auth.spec.ts
    ├── dashboard.spec.ts
    ├── notes.spec.ts
    ├── settings.spec.ts
    └── pwa.spec.ts
```

---

## 6. API client generation

### 6.1 Generation

`openapi-ts.config.ts` MUST be:

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

`openapi.json` is produced by the backend's `./dev openapi` (PLATFORM-SPEC §24).

### 6.2 Rules

- `pnpm api:generate` regenerates. The output **MUST be committed** so a clean checkout builds without a running backend.
- Generated files are treated as read-only. The implementer MUST NOT hand-edit anything under `src/api/generated/`. ESLint MUST ignore that directory; TypeScript MUST still type-check it.
- All request and response types used anywhere in the app MUST come from `types.gen.ts`. Hand-written interfaces mirroring API shapes are forbidden.
- CI MUST run `pnpm api:generate` and fail if the working tree becomes dirty, proving the committed client matches the current API.
- PLATFORM-SPEC §17.7 guarantees stable `operation_id`s, so generated method names are stable. If a generated name changes, that is an API change and must be reviewed, not absorbed silently.

---

## 7. HTTP layer and error mapping

### 7.1 Client configuration

`src/api/client.ts` MUST configure the generated fetch client with:

- `baseUrl: '/api'`
- `credentials: 'same-origin'`
- A request interceptor adding `Authorization: Bearer <access token>` when one is held in memory, and **omitting the header entirely** when none is.
- A request interceptor adding `X-Requested-With: mystuff` to `POST /auth/refresh` and `POST /auth/logout` only (PLATFORM-SPEC §10.5).
- A response interceptor implementing the 401 refresh flow (§8.4).
- A default timeout of 15 seconds via `AbortSignal.timeout(15_000)`.

### 7.2 Problem details

`src/api/problem.ts` MUST define:

```ts
export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  code: string;                 // PLATFORM-SPEC Appendix A
  request_id: string;
  errors?: Array<{ loc: (string | number)[]; msg: string; type: string }>;
}

export function parseProblem(res: Response, body: unknown): ProblemDetail
export function isProblem(value: unknown): value is ProblemDetail
```

`parseProblem` MUST tolerate a non-conforming body (an HTML error page from a proxy, an empty body) and synthesise a `ProblemDetail` with `code: 'internal_error'` rather than throwing.

### 7.3 Error presentation rules

| Server `code` | Client behaviour |
|---|---|
| `auth.refresh_token_reused` | Hard logout (§8.6). Persistent red banner with the security copy in Appendix D. |
| any other `401` | Attempt refresh once (§8.4); if that fails, soft logout and redirect to `/login?next=<path>` |
| `403 acl.forbidden` | Inline error on the affected control; toast "You don't have permission to do that." |
| `403 auth.admin_required` | Route guard should have prevented it; render the 403 screen |
| `404` | Route-level: 404 screen. Item-level: toast + invalidate the containing list query |
| `409` | Inline field error where a field is implicated (`auth.user_exists` → email field); otherwise toast |
| `410 auth.invite_expired` | Dedicated screen state on `/accept-invite` with copy from Appendix D |
| `422` | Map `errors[].loc` to form fields via §19.3; unmapped entries become a form-level error |
| `429` | Toast with the `Retry-After` value rendered as "Try again in N seconds"; disable the submit button for that duration |
| `5xx` | Toast "Something went wrong on the server." plus the `request_id` in small text, copyable |
| Network failure | If `navigator.onLine === false`, show the offline copy; otherwise the generic network copy |

The client MUST NOT display the raw `detail` string for `5xx` responses (PLATFORM-SPEC §17.4 guarantees it is generic, but the client MUST NOT depend on that). For `4xx` responses the `detail` string is safe to display and SHOULD be preferred over generic copy.

The `request_id` MUST be surfaced somewhere for any `5xx` — this is the only thread between a user's report and a server log line.

---

## 8. Authentication in the browser

This section is normative in its entirety and is the highest-risk part of the client.

### 8.1 Token storage

`src/auth/tokenStore.ts` MUST expose:

```ts
let accessToken: string | null = null;
let expiresAt: number | null = null;          // epoch ms

export function setToken(token: string, expiresInSeconds: number): void
export function getToken(): string | null
export function clearToken(): void
export function isExpiringWithin(ms: number): boolean
```

The implementer MUST NOT write the access token, the refresh token, or the user's password to `localStorage`, `sessionStorage`, IndexedDB, the Cache API, a cookie set from JavaScript, or the URL. An automated test asserts this (§23.3, case 12).

**Permitted `localStorage` keys — exhaustive:**

| Key | Value | Purpose |
|---|---|---|
| `mystuff.theme` | `"light" \| "dark" \| "system"` | Theme override |
| `mystuff.installDismissedAt` | epoch ms | Install-prompt suppression |

Nothing else. No user id, no email, no route history.

### 8.2 Auth states

```ts
type AuthState =
  | { status: 'loading' }
  | { status: 'anonymous' }
  | { status: 'authenticated'; user: UserOut }
  | { status: 'revoked'; reason: 'reuse_detected' };
```

`revoked` is distinct from `anonymous` because it must produce a visible security warning rather than a silent redirect.

### 8.3 Bootstrap sequence

On application mount, `AuthProvider` MUST:

1. Set state `loading`. Render a full-page skeleton — **not** a redirect, and **not** the login screen.
2. Call `POST /api/auth/refresh` with `X-Requested-With: mystuff` and `credentials: 'same-origin'`.
3. On `200`: store the access token in memory, schedule proactive refresh (§8.5), call `GET /api/auth/me`, set state `authenticated`.
4. On `401 auth.refresh_token_reused`: set state `revoked`.
5. On any other `401`/`403`: set state `anonymous`.
6. On network failure: if a cached `GET /api/auth/me` response exists in the query cache **and** the app is offline, enter a degraded read-only authenticated state (§18.4). Otherwise set state `anonymous`.

The bootstrap request MUST complete before any authenticated route renders. Route loaders MUST await it.

### 8.4 Reactive refresh (single-flight)

The response interceptor MUST implement exactly this:

1. If the response status is not `401`, return it unchanged.
2. If the failed request was itself `/auth/refresh`, `/auth/login`, `/auth/logout`, or `/auth/accept-invite`, do not retry — return the response.
3. If the problem `code` is `auth.refresh_token_reused`, trigger hard logout (§8.6) and return.
4. If the request has already been retried once (tracked with a symbol on the request init), return the response.
5. If a refresh is already in flight, await the existing promise. Otherwise start one and store the promise so concurrent 401s share it. **There MUST be at most one in-flight refresh per tab.**
6. If refresh succeeds, replay the original request once with the new token and return that response.
7. If refresh fails, soft logout and return the original `401`.

### 8.5 Proactive refresh

After a successful login or refresh, schedule a timer for `expires_in - 60` seconds (minimum 30 seconds) that calls refresh. The timer MUST be cleared on logout and on `visibilitychange` to hidden, and re-evaluated on `visibilitychange` to visible: if the token is expired or expires within 60 seconds, refresh immediately before resuming.

Rationale: a phone that has been asleep for an hour returns with a dead token; refreshing on wake avoids a burst of 401s.

### 8.6 Logout

**Soft logout** (token invalid, session simply over): clear the in-memory token, clear the TanStack Query cache, purge all Cache Storage entries whose URL contains `/api/` (§18.5), set state `anonymous`, navigate to `/login?next=<current path>`.

**Explicit logout** (user pressed the button): call `POST /api/auth/logout`, then perform the soft-logout steps, then navigate to `/login` with no `next`.

**Hard logout** (`auth.refresh_token_reused`): perform the soft-logout steps, set state `revoked`, navigate to `/login`, and render the persistent security banner. The banner MUST remain until the user dismisses it explicitly.

Cache purging on every logout path is mandatory: cached API responses in Cache Storage survive a page reload and would otherwise be readable by the next user of a shared device.

### 8.7 Login screen (`/login`)

- Fields: email (`type="email"`, `autocomplete="username"`), password (`type="password"`, `autocomplete="current-password"`).
- Submit calls `POST /api/auth/login`. On `200`, store the token, invalidate `['auth','me']`, and navigate to `next` if it is a same-origin relative path beginning with `/`, otherwise to `/`. An absolute or protocol-relative `next` MUST be ignored (open-redirect defence).
- `401 auth.invalid_credentials` → a single form-level error using the copy in Appendix D. The client MUST NOT distinguish unknown-email from wrong-password, mirroring PLATFORM-SPEC §10.4.
- `403 auth.account_disabled` → form-level error with distinct copy.
- `429` → disable submit for the `Retry-After` duration with a live countdown.
- The submit button MUST be disabled while in flight and MUST show a spinner. Double-submit MUST be impossible.
- No "remember me" checkbox — the refresh cookie's 30-day lifetime is the only persistence.
- No password-reset link — PLATFORM-SPEC has no such flow. The screen MUST show static copy directing the user to contact the administrator.

### 8.8 Invite acceptance (`/accept-invite`)

Reads `token` from the query string. Fields: display name, password, confirm password. Client-side policy mirrors PLATFORM-SPEC §10.3 (≥12 chars, ≤128, not equal to the invited email) with a strength meter that is advisory only. On success the server returns a session; store the token and navigate to `/`.

Distinct screen states for `404 auth.invite_not_found`, `409 auth.invite_used`, and `410 auth.invite_expired`, each with copy from Appendix D and no form rendered.

### 8.9 What the client MUST NOT do

- MUST NOT create, read, or store a personal access token. PATs are for the CLI (PLATFORM-SPEC §10.7); the browser uses cookie + access token exclusively. The *management* UI at `/settings/tokens` (§15.2) lists and revokes tokens but never uses one for its own requests, and displays a newly created token exactly once without persisting it.
- MUST NOT attempt to read the refresh cookie.
- MUST NOT decode the access token to extract claims. User identity comes from `GET /api/auth/me`.

---

## 9. Routing

TanStack Router with file-based routes and typed params. All authenticated routes nest under the `_app` layout, which owns the guard.

| Path | Component | Guard | Document title |
|---|---|---|---|
| `/login` | Login | anonymous-only (redirect to `/` if authenticated) | `Sign in · MyStuff` |
| `/accept-invite` | AcceptInvite | none | `Accept invitation · MyStuff` |
| `/` | Dashboard | auth | `Dashboard · MyStuff` |
| `/notes` | NotesList | auth | `Notes · MyStuff` |
| `/notes/:noteId` | NoteDetail | auth | `<note title> · MyStuff` |
| `/settings` | SettingsIndex | auth | `Settings · MyStuff` |
| `/settings/account` | Account | auth | `Account · MyStuff` |
| `/settings/tokens` | Tokens | auth | `API tokens · MyStuff` |
| `/settings/:domain` | ModuleSettings | auth | `<panel title> · MyStuff` |
| `/admin/invites` | Invites | auth + `is_admin` | `Invitations · MyStuff` |
| `*` | NotFound | none | `Not found · MyStuff` |

Rules:

- The `_app` guard MUST await auth bootstrap. While `loading`, render the shell skeleton — never flash the login screen.
- Unauthenticated access to a guarded route redirects to `/login?next=<pathname+search>`.
- A non-admin reaching `/admin/*` renders a 403 screen; it MUST NOT redirect, so the URL stays honest.
- `/settings/:domain` MUST validate `domain` against the manifest's settings panels and render the 404 screen for an unknown domain, without a network call.
- Route-level code splitting is mandatory: every route is a lazy chunk.
- Scroll position resets to top on navigation except on back/forward, where it restores.
- `document.title` is set by each route.

---

## 10. Server state management

### 10.1 Query client defaults

```ts
new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: (failureCount, error) =>
        !isProblem(error) && failureCount < 2,     // never retry 4xx
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
      throwOnError: false,
    },
    mutations: { retry: false },
  },
});
```

Mutations MUST NOT be retried automatically — a duplicated `POST /api/notes` creates a duplicate note.

### 10.2 Per-query configuration

| Query | `staleTime` | Refetch on focus | Notes |
|---|---|---|---|
| `['auth','me']` | 5 min | no | Invalidated on login/logout |
| `['dashboard','manifest']` | 10 min | no | Rarely changes; drives navigation |
| `['dashboard','tiles']` | 0 | yes | Always considered stale |
| `['dashboard','tile', key]` | per tile `refresh_seconds` | yes | §13.4 |
| `['notes','list', filters]` | 30 s | yes | Infinite query |
| `['notes','detail', id]` | 60 s | yes | |
| `['settings', domain]` | 60 s | no | |
| `['auth','tokens']` | 30 s | no | |
| `['auth','invites']` | 30 s | no | Admin only |

### 10.3 Invalidation matrix

| Mutation | Invalidates |
|---|---|
| Create note | `['notes','list']`, `['dashboard','tile','notes.latest']` |
| Update note | `['notes','list']`, `['notes','detail',id]`, `['dashboard','tile','notes.latest']` |
| Delete note | `['notes','list']`, `['dashboard','tile','notes.latest']`; removes `['notes','detail',id]` |
| Share note | `['notes','detail',id]` |
| Tile action | `['dashboard','tile',key]` and any query key listed in §13.6 |
| Save settings | `['settings',domain]` |
| Create/revoke token | `['auth','tokens']` |
| Create/delete invite | `['auth','invites']` |
| Change password | nothing (server revokes other sessions; the caller's stays valid) |

### 10.4 Optimistic updates

Optimistic updates are permitted for exactly three operations, each of which MUST implement `onMutate` snapshot, `onError` rollback, and `onSettled` invalidation:

1. Toggling a note's `pinned` flag.
2. Deleting a note from the list (row disappears immediately).
3. Quick-add from the notes tile (an item appears at the top with a pending indicator).

All other mutations render a pending state and wait for the server. Optimism where the server may reasonably reject is a correctness bug, not a UX improvement.

### 10.5 Pagination

`GET /api/notes` uses cursor pagination (PLATFORM-SPEC §17.5). The client MUST use `useInfiniteQuery` with `getNextPageParam: (last) => last.next_cursor ?? undefined`. The list uses an explicit "Load more" button, not scroll-triggered auto-loading — infinite scroll makes the footer unreachable and is a poor fit for a list users search rather than browse.

---

## 11. Design system

### 11.1 Principles

The interface is a personal control centre used daily, often one-handed on a phone, often for five seconds at a time. It therefore favours: high information density on desktop, generous touch targets on mobile, calm neutral surfaces with one accent colour, and no decorative motion.

### 11.2 Tokens

Design tokens are CSS custom properties defined in `src/styles/index.css` and consumed through Tailwind v4's `@theme` directive. The full token table is Appendix C. The implementer MUST NOT use raw hex values or arbitrary Tailwind values (`text-[#3b82f6]`) anywhere in components.

### 11.3 Colour and theme

- Two themes: light and dark, plus `system` which follows `prefers-color-scheme`.
- Theme is applied by setting `data-theme="light|dark"` on `<html>`. The resolved theme MUST be applied by a small inline script in `index.html` **before** first paint, to prevent a flash of the wrong theme.
- The `<meta name="theme-color">` MUST be updated to match the resolved theme so the mobile browser chrome matches.
- Semantic tokens only: `--color-surface`, `--color-surface-raised`, `--color-text`, `--color-text-muted`, `--color-border`, `--color-accent`, `--color-danger`, `--color-success`, `--color-warning`. Components reference semantics, never palette steps.

### 11.4 Typography

- System font stack; no web fonts. This removes a render-blocking request and a licensing question, and every platform's system font is already optimised for its screens.
- Scale (rem): `0.75, 0.875, 1, 1.125, 1.25, 1.5, 2`. Body text is `1rem` on mobile and `0.9375rem` on desktop where density matters.
- Line height: 1.5 for body, 1.25 for headings.
- Maximum measure for prose (note bodies): `68ch`.

### 11.5 Spacing, radius, elevation

- Spacing scale is Tailwind's default 4px base. Layout gaps use `4, 8, 12, 16, 24, 32, 48`.
- Radius: `--radius-sm: 6px`, `--radius-md: 10px`, `--radius-lg: 16px`. Cards use `md`, dialogs `lg`, controls `sm`.
- Elevation is expressed with borders and subtle background steps, not shadows, except for overlays (dialogs, dropdowns, toasts) which use one shadow token.

### 11.6 Breakpoints

| Name | Min width | Layout |
|---|---|---|
| `base` | 0 | Single column, bottom navigation |
| `sm` | 640px | Single column, wider gutters |
| `md` | 768px | Two-column tile grid, side navigation appears |
| `lg` | 1024px | Three-column tile grid |
| `xl` | 1280px | Three columns, max content width 1200px, centred |

Mobile-first: base styles are mobile, breakpoints add.

### 11.7 Motion

- Durations: 120ms for state changes, 200ms for overlays. Easing `cubic-bezier(0.2, 0, 0, 1)`.
- Every transition MUST be wrapped so that `@media (prefers-reduced-motion: reduce)` reduces it to `0ms`.
- No parallax, no scroll-linked animation, no skeleton shimmer (a static muted block is sufficient and cheaper).

---

## 12. Application shell and navigation

### 12.1 Structure

```
┌──────────────────────────────────────────┐
│ TopBar: logo · page title · user menu    │  ← md and up: also global search slot (unused v1)
├────────┬─────────────────────────────────┤
│ SideNav│  <Outlet />                     │  ← md and up only
│ (md+)  │                                 │
└────────┴─────────────────────────────────┘
┌──────────────────────────────────────────┐
│ BottomNav (base–sm only)                 │
└──────────────────────────────────────────┘
```

### 12.2 Navigation items

Built from `['dashboard','manifest']` plus fixed entries:

| Order | Label | Icon | Path | Visibility |
|---|---|---|---|---|
| 1 | Dashboard | `layout-dashboard` | `/` | always |
| 2 | Notes | `sticky-note` | `/notes` | when the `notes` module is in the manifest |
| 3 | Settings | `settings` | `/settings` | always |
| 4 | Invitations | `user-plus` | `/admin/invites` | `is_admin` only, desktop side nav only |

**Module-driven navigation rule:** a module that registers tiles but has no bespoke screen appears only on the dashboard. Only modules with an entry in a hard-coded `MODULE_ROUTES` map (v1: `notes` alone) get a nav item. This is deliberate — bespoke screens require bespoke code, and the client must not pretend otherwise. `MODULE_ROUTES` MUST be a single, clearly commented constant so adding a future module's screen is a one-line change plus the screen itself.

### 12.3 Mobile bottom navigation

- Fixed to the bottom, respecting `env(safe-area-inset-bottom)`.
- Maximum four items; if more exist, the fourth becomes "More" opening a sheet.
- Each target ≥ 56px tall, ≥ 64px wide.
- The active item is indicated by icon fill and label colour, not by colour alone (§21).

### 12.4 User menu

Radix dropdown in the top bar: display name and email (truncated), then Account, API tokens, Theme submenu (Light/Dark/System), and Sign out. Sign out uses the explicit-logout path (§8.6).

### 12.5 Safe areas and viewport

`index.html` MUST set:

```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
```

The shell MUST pad with `env(safe-area-inset-*)` on all four sides where content would otherwise sit under system UI.

---

## 13. Dashboard and generic tile rendering

This is the core of the client and the requirement most likely to be implemented wrongly. **No component in `src/components/tiles/` may contain a conditional on a specific tile key or module domain.**

### 13.1 Data flow

1. `GET /api/dashboard/manifest` → the list of `TileSpec`s across all modules, each with `key`, `title`, `size`, `refresh_seconds`, `order`.
2. `GET /api/dashboard/tiles` → an array of `TileData`, one per tile, on first render.
3. Thereafter each tile refreshes independently via `GET /api/dashboard/tiles/{key}` (§13.4).

The manifest determines *which tiles exist and how they are laid out*; the tile endpoints determine *what they contain*. The client never assumes a tile exists.

### 13.2 Grid layout

| Breakpoint | Columns | `small` | `medium` | `large` |
|---|---|---|---|---|
| base | 1 | 1 col | 1 col | 1 col |
| md | 2 | 1 col | 1 col | 2 cols |
| lg | 3 | 1 col | 1 col | 2 cols |
| xl | 3 | 1 col | 1 col | 2 cols |

CSS Grid with `grid-auto-rows: min-content` and `align-items: start` so tiles do not stretch to match their tallest neighbour. Order is `TileSpec.order` ascending, then `key` ascending — a stable, server-controlled sort.

An unknown `size` value MUST fall back to `medium` rather than breaking layout. This matters: a future module may ship a size this client predates.

### 13.3 `TileCard` anatomy

```
┌─────────────────────────────────────┐
│ Title                    [count]  ⋯ │   header
├─────────────────────────────────────┤
│ • primary text          secondary   │   items (max 5 rendered)
│   timestamp                         │
│ • …                                 │
├─────────────────────────────────────┤
│ [Action]  [Action]                  │   footer, only if actions exist
└─────────────────────────────────────┘
```

Rules:
- `count` renders as a badge only when non-null. `count: 0` renders "0", not nothing.
- At most five `items` are rendered regardless of how many arrive; if more arrive, a muted "+N more" line follows. The server is expected to send few, but the client MUST NOT assume it.
- When `items` is empty, render `empty_text` in muted italic. Actions still render.
- `generated_at` is rendered as a relative timestamp ("updated 2 min ago") in the header on hover/focus only (a `title` attribute plus visually-hidden text), to avoid visual noise.
- The whole card is **not** a link. Only `TileItem.href` values are links.

### 13.4 Per-tile refresh

Each tile mounts a `useQuery` for `['dashboard','tile', key]` with `refetchInterval: refresh_seconds * 1000` and `staleTime: refresh_seconds * 1000`, seeded from the bulk `GET /api/dashboard/tiles` response via `initialData`.

Refresh MUST pause when the document is hidden (`refetchIntervalInBackground: false`) and resume on visibility, immediately refetching any tile whose interval elapsed while hidden.

### 13.5 `TileItem` rendering

| Field | Rendering |
|---|---|
| `primary` | Primary line, single line, `text-overflow: ellipsis` |
| `secondary` | Muted, appended inline on `md`+, on its own line below on mobile |
| `timestamp` | Relative ("2h ago") with the absolute value in `title` and a `<time datetime>` element |
| `done` | When non-null, a **read-only** checkbox (see the limitation below) |
| `href` | Wraps `primary` in a router link when the value starts with `/api/`, translated per §13.7; otherwise renders as plain text |

**Known limitation — item-level actions.** PLATFORM-SPEC §8.2 defines `TileAction` at tile level with a fixed `path`; there is no mechanism binding an action to a specific item. Therefore `done` is **display-only** in v1: it renders state, it does not toggle it. The implementer MUST render it with `disabled` and `aria-readonly="true"`, and MUST NOT invent a URL template convention. Making checkboxes interactive requires a backbone contract amendment (adding per-item actions to `TileItem`) and is explicitly out of scope for this version.

### 13.6 Tile actions

`TileAction` has `id`, `label`, `method`, `path`, and optional `body_schema`.

- **No `body_schema`:** clicking issues the request immediately. For `method: "DELETE"`, a confirmation dialog is required first.
- **With `body_schema`:** clicking opens `TileActionDialog` containing a `SchemaForm` (§14) generated from that JSON Schema. Submit issues the request with the form value as the JSON body.

After a successful action the client MUST invalidate `['dashboard','tile', <the tile's key>]` and, additionally, any query key whose first segment matches the action path's module domain (e.g. an action on `/api/notes` invalidates `['notes']`). This is a generic rule derived from the path, not a per-module special case.

Errors follow §7.3. A failed action leaves the dialog open with the error rendered inline so input is not lost.

### 13.7 `href` translation

`TileItem.href` values are API paths (`/api/notes/{id}`). The client maps them to UI routes with a single generic rule: strip the `/api` prefix and look the result up in `MODULE_ROUTES` (§12.2). `/api/notes/abc` → `/notes/abc`. A path with no mapping renders as plain text, not a broken link.

### 13.8 Tile failure and loading

- Loading: `TileSkeleton` — a card of the correct size with three muted bars. No shimmer.
- The server already substitutes a fallback tile for a failed provider (PLATFORM-SPEC §16.2), so a "failed" tile arrives as valid `TileData` with `empty_text: "This tile failed to load"`. The client renders it normally — it MUST NOT special-case that string.
- If the tile *request itself* fails (network, 5xx), render `TileError`: the tile title, a muted error line, and a Retry button that refetches only that tile.
- One failing tile MUST NOT affect any other tile. Each tile is wrapped in its own error boundary.

### 13.9 Empty dashboard

When the manifest contains no tiles, render an `EmptyState` with the copy in Appendix D directing the user to the modules documentation. This is a real state on a fresh install with no modules enabled.

---

## 14. Generic settings rendering

### 14.1 Data flow

1. `['dashboard','manifest']` provides each module's settings panels, including the JSON Schema (amendment A1).
2. `GET /api/settings/{domain}` returns current values, secrets masked as `"***"`.
3. `PUT /api/settings/{domain}` saves. Only changed keys are sent.

`/settings` (index) lists every panel across all modules, grouped by module, plus the fixed Account and API tokens entries. `/settings/:domain` renders that module's panels.

### 14.2 Why not a library

`@rjsf/core` is forbidden. It is large (>100 KB), imposes its own theming, and produces markup that fails the accessibility requirements in §21 without extensive overrides. The subset of JSON Schema the backend emits is small and fully enumerated in Appendix B; a purpose-built renderer of roughly 300 lines is smaller, more accessible, and more predictable.

### 14.3 `SchemaForm`

`SchemaForm` accepts a JSON Schema, an initial value, and an `onSubmit`, and MUST:

1. Convert the schema to a Zod schema via `schemaToZod.ts` for client-side validation (Appendix B).
2. Render fields via `fieldFor.tsx`, dispatching on `type`, `format`, `enum`, and `x-secret`.
3. Use `title` for the label, `description` for help text, and `default` for the initial value when the current value is absent.
4. Mark fields listed in `required` and set `aria-required`.
5. Render an unsupported schema construct as a **disabled** field with the text "This setting can't be edited here." rather than crashing or silently dropping it. Forward compatibility matters: a future module may emit a construct this client predates.
6. Track dirty state per field and send only changed keys on submit.
7. Warn on navigation away with unsaved changes, using the router's `blocker`.

### 14.4 Secret fields

A property with `"x-secret": true` (amendment A2):

- Renders as `type="password"` with `autocomplete="off"`.
- When the current value is `"***"`, render the field empty with the placeholder "Saved — leave blank to keep" and a muted "Set" badge.
- When the current value is `null`, render empty with a "Not set" badge.
- On submit, an untouched secret field MUST be **omitted from the payload entirely**. The client MUST NOT send the literal `"***"` back, even though the server tolerates it — omission is unambiguous.
- A "Clear" button next to a set secret sends `null` for that key.
- Secret values MUST NOT be logged, placed in error messages, or included in any toast.

### 14.5 Save behaviour

Optimistic updates are forbidden here. The form disables during the request, shows a spinner on the submit button, and on success shows a success toast and resets dirty state to the server's response. `422` maps to field errors (§19.3). `500 settings.decryption_failed` shows a distinct, non-generic message (Appendix D) because it indicates a server key problem the user must escalate, not retry.

---

## 15. Account, tokens, and admin screens

### 15.1 `/settings/account`

- Read-only display of display name, email, admin status, and account creation date.
- **Change password** form: current password, new password, confirm. `autocomplete` values `current-password` and `new-password`. Client-side policy mirrors §8.8. On success, a toast explaining that other sessions were signed out (PLATFORM-SPEC §10.10) and the form resets. `422 auth.password_policy` renders the server's `detail` on the new-password field.
- The client MUST note in helper text that this form is unavailable when signed in with an API token — although the browser never uses one, the copy documents the server's rule truthfully.

### 15.2 `/settings/tokens`

Manages PATs used by the CLI. The browser never authenticates with these.

- Table: name, prefix, created, last used (relative, "Never" when null), expires ("Never" when null), and a Revoke action.
- **Create** dialog: name (required, ≤64 chars), optional expiry in days. On success, the plaintext token is displayed **once** in a dialog with a copy button, a warning that it will not be shown again, and an explicit "I've saved it" dismissal. The value MUST NOT be written to any store, MUST NOT appear in the query cache after the dialog closes, and MUST be cleared from component state on unmount.
- **Revoke** requires confirmation naming the token.
- Helper text explains that these are for the `stuff` CLI and links to the CLI docs.

### 15.3 `/admin/invites`

Admin-only.

- Table of pending invites: email, created by, expires (relative), and a Revoke action.
- **Create** dialog: email (required), "Grant admin access" switch. On success, display the `accept_url` once with a copy button and copy explaining that the system sends no email and the link must be delivered by the admin personally.
- `409 auth.user_exists` and `409 auth.invite_pending` map to the email field with distinct messages.
- The invite token MUST NOT be logged or persisted.

---

## 16. Notes screens

The `notes` module gets bespoke screens, demonstrating that a module can exceed what a tile expresses. Everything here uses only the generated client.

### 16.1 `/notes` — list

**Toolbar:** search input (debounced 300ms, bound to `q`), a pinned-only filter toggle, and a "New note" button.

**List:** `useInfiniteQuery` on `['notes','list',{q,pinned}]`. Server ordering is `pinned DESC, created_at DESC` (PLATFORM-SPEC §18.3) and the client MUST NOT re-sort.

**Row (`NoteCard`):** pin indicator, title (or the first line of body when title is null), a two-line body preview, relative created time, and an overflow menu (Open, Pin/Unpin, Share, Delete).

- Clicking a row navigates to `/notes/:id`.
- Pin toggling is optimistic (§10.4).
- Delete asks for confirmation, then removes the row optimistically.
- The search term is reflected in the URL (`?q=`) so a search is linkable and survives reload.

**States:** loading (three skeleton rows), empty with no filters (EmptyState with a "Create your first note" CTA), empty with filters ("No notes match" plus a Clear filters button), error (retry).

### 16.2 `/notes/:noteId` — detail

- Header: title (or "Untitled"), pin toggle, overflow menu (Share, Delete), Back.
- Body rendered as **plain text with preserved whitespace** (`white-space: pre-wrap`). Markdown is **not** rendered — PLATFORM-SPEC defines `body` as plain text, and rendering it as Markdown would misrepresent stored data and add an XSS surface. The implementer MUST NOT add a Markdown renderer.
- Metadata: created and updated timestamps, absolute, locale-formatted.
- Edit is inline: clicking the body or the Edit button switches to a textarea with Save and Cancel. `Cmd/Ctrl+Enter` saves, `Escape` cancels with an unsaved-changes confirmation.
- `404 notes.not_found` renders the not-found screen, not a toast.

### 16.3 Note creation

A dialog reachable from the list toolbar, from the dashboard tile's quick-add action, and from a keyboard shortcut. Fields: title (optional), body (required, autofocused, ≤20000 chars with a counter appearing past 19000), pin switch. `Cmd/Ctrl+Enter` submits.

On success: close, toast with an "Open" action linking to the new note, invalidate per §10.3.

### 16.4 Sharing

`ShareDialog` on a note: email input and a read/write radio group, calling `POST /api/notes/{id}/share`.

- `404 notes.user_not_found` → email field error, "No user with that email. They need an account first."
- `400 notes.cannot_share_with_self` → email field error.
- `403` → the dialog closes with a toast; only owners may share.
- PLATFORM-SPEC provides no endpoint listing a note's existing grants, so the dialog MUST NOT display current shares. It states plainly that sharing is additive and that removing access requires the API. The implementer MUST NOT invent an endpoint.

### 16.5 Keyboard shortcuts

Global, active only when no input has focus:

| Key | Action |
|---|---|
| `g` then `d` | Go to dashboard |
| `g` then `n` | Go to notes |
| `n` | New note dialog |
| `/` | Focus search (on `/notes`) |
| `?` | Show shortcuts dialog |
| `Escape` | Close topmost overlay |

---

## 17. PWA behaviour

### 17.1 Web app manifest

Generated by `vite-plugin-pwa`:

```json
{
  "name": "MyStuff",
  "short_name": "MyStuff",
  "description": "Your personal control centre",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "orientation": "any",
  "background_color": "#ffffff",
  "theme_color": "#ffffff",
  "icons": [
    {"src":"/icons/icon-192.png","sizes":"192x192","type":"image/png"},
    {"src":"/icons/icon-512.png","sizes":"512x512","type":"image/png"},
    {"src":"/icons/icon-maskable-192.png","sizes":"192x192","type":"image/png","purpose":"maskable"},
    {"src":"/icons/icon-maskable-512.png","sizes":"512x512","type":"image/png","purpose":"maskable"}
  ],
  "shortcuts": [
    {"name":"New note","url":"/notes?new=1","icons":[{"src":"/icons/icon-192.png","sizes":"192x192"}]}
  ]
}
```

Maskable icons MUST respect the 40% safe zone. `theme_color` MUST match the light theme surface; the runtime `<meta name="theme-color">` is updated on theme change (§11.3).

### 17.2 iOS specifics

`index.html` MUST include `<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">` and `<meta name="apple-mobile-web-app-title" content="MyStuff">`. Safe-area padding (§12.5) is mandatory — without it the bottom navigation sits under the home indicator.

### 17.3 Install prompt

- Capture `beforeinstallprompt`, prevent default, store the event.
- Show a dismissible install card on the dashboard, but only when: the event was captured, the app is not already in standalone mode, and `mystuff.installDismissedAt` is absent or older than 30 days.
- Dismissal writes the timestamp. The card MUST NOT be a modal or block content.
- iOS fires no such event; on iOS Safari (not standalone) show a one-line hint describing Share → Add to Home Screen, under the same 30-day dismissal rule.

### 17.4 Update flow

`registerType: 'prompt'`. When a new service worker is waiting, show a non-blocking toast: "A new version is available." with a Reload action calling `updateSW(true)`.

The app MUST NOT auto-reload — doing so mid-edit destroys unsaved input. If the user has unsaved changes, the toast persists until they act.

---

## 18. Offline strategy

### 18.1 Scope

The app is **read-only offline**. Cached data is viewable; mutations require a connection. There is no background sync and no offline write queue — an offline mutation queue for a multi-user shared-resource app raises conflict questions this version does not answer, and a half-implemented one loses data.

### 18.2 Runtime caching rules

| Route pattern | Strategy | Expiry | Notes |
|---|---|---|---|
| App shell (JS/CSS/HTML/icons) | Precache | — | Revisioned by build hash |
| `/api/auth/**` | **NetworkOnly** | — | Never cached, ever |
| `/api/dashboard/manifest` | StaleWhileRevalidate | 24h, 1 entry | |
| `/api/dashboard/tiles*` | NetworkFirst, 3s timeout | 1h, 20 entries | |
| `/api/notes` (GET) | NetworkFirst, 3s timeout | 24h, 30 entries | |
| `/api/notes/*` (GET) | NetworkFirst, 3s timeout | 24h, 50 entries | |
| `/api/settings/*` | NetworkFirst, 3s timeout | 1h, 10 entries | |
| Any non-GET `/api/**` | **NetworkOnly** | — | Never cached |

Only `200` responses are cached. Navigation requests fall back to the precached `index.html`, excluding any URL beginning with `/api`.

### 18.3 Cache and credentials

Cached API responses contain the user's data. Therefore:

- Every logout path purges all Cache Storage entries whose request URL contains `/api/` (§8.6).
- The service worker MUST NOT cache any response to a request bearing an `Authorization` header **other than** GETs matching the table above. Non-GET methods are never cached under any circumstance.
- The cache name MUST include the app version so a deploy invalidates stale API caches.

### 18.4 Degraded authenticated mode

If bootstrap refresh fails purely because the device is offline (`navigator.onLine === false` and the failure is a transport error, not a `401`), the app MAY render authenticated routes in read-only mode using cached data, with the offline banner shown and every mutating control disabled. It MUST NOT do this when the server actively rejected the refresh — an expired or revoked session must sign the user out.

### 18.5 Offline UX

- `OfflineBanner` appears at the top of the shell whenever `navigator.onLine` is false, using `online`/`offline` events plus a periodic lightweight `HEAD /health/live` check every 30 seconds while offline (browsers report `onLine` optimistically).
- All mutating controls are disabled while offline, with a tooltip "You're offline."
- Data rendered from cache while offline is labelled with a subtle "Showing saved data" line in each affected view.
- On reconnect, TanStack Query's `refetchOnReconnect` refreshes everything; the banner disappears with no reload.

---

## 19. Forms and validation

### 19.1 Library usage

`react-hook-form` with a `zodResolver`. Uncontrolled inputs by default; controlled only where a Radix primitive requires it.

### 19.2 Client-side rules

Client validation exists to give fast feedback, never to replace server validation. Every constraint below mirrors a server constraint and MUST be kept in sync with PLATFORM-SPEC:

| Field | Rule | Source |
|---|---|---|
| Email | non-empty, valid format, ≤254 | §10.4 |
| Password (new) | ≥12, ≤128, ≠ email | §10.3 |
| Display name | 1–100 | §6.2 |
| Note title | 0–200 (empty → `null`) | §18.2 |
| Note body | 1–20000 | §18.2 |
| Token name | 1–64 | §6.2 |
| Search `q` | ≤200 | §18.3 |

### 19.3 Mapping `422` to fields

PLATFORM-SPEC §17.3 returns `errors: [{loc, msg, type}]`. `loc` is a path such as `["body","email"]`. The client MUST:

1. Drop a leading `"body"`, `"query"`, or `"path"` segment.
2. Join the remainder with `.` to form the react-hook-form field name.
3. Call `setError(fieldName, { message: msg })`.
4. If the field does not exist in the form, attach the message to a form-level error region instead of discarding it.

### 19.4 Behaviour

- Validate on blur and on submit; re-validate on change only after the first failed submit.
- The submit button is disabled while submitting, never while merely invalid — disabling on invalid hides the reason for failure.
- The first invalid field receives focus on failed submit.
- Errors render below the field, associated with `aria-describedby`, and the field gets `aria-invalid="true"`.
- Destructive confirmations (delete note, revoke token, revoke invite) require a distinct confirm button labelled with the verb ("Delete note"), never "OK".

---

## 20. Feedback, errors, and empty states

### 20.1 Toasts

Radix Toast, bottom-centre on mobile and bottom-right on desktop, above the bottom navigation.

- Variants: success (4s), error (8s), info (5s). Errors are dismissible and pause on hover/focus.
- Maximum three concurrent; older ones collapse.
- The region is `aria-live="polite"` for success/info and `aria-live="assertive"` for errors.
- Toasts MUST NOT be the only channel for an error that has a natural inline home (form fields, tile bodies).

### 20.2 Error boundaries

Three levels, each with its own recovery:

1. **Root** — catches render crashes, shows a full-page error with Reload and the build version.
2. **Route** — catches per-route errors, keeps the shell and navigation usable.
3. **Tile** — one per tile (§13.8).

A boundary MUST log to `console.error` and MUST NOT send anything anywhere (no telemetry, §1.2).

### 20.3 Loading

- Route transitions: a 2px indeterminate progress bar under the top bar, appearing only after 150ms so fast navigations do not flash.
- Lists and tiles: skeletons matching the final layout's dimensions to avoid layout shift.
- Buttons: an inline spinner replacing the label's leading icon, with the label retained. The button width MUST NOT change.

### 20.4 Empty states

Every list and tile has a defined empty state with an icon, a one-line explanation, and, where an action makes sense, a primary button. Copy is in Appendix D. An empty state MUST NOT be an unstyled "No data".

---

## 21. Accessibility

Target: **WCAG 2.2 Level AA**. These are requirements, not aspirations.

| # | Requirement |
|---|---|
| A1 | Contrast ≥ 4.5:1 for body text and ≥ 3:1 for large text and UI component boundaries, in both themes. |
| A2 | Every interactive element is reachable and operable by keyboard, in a logical DOM order. |
| A3 | Visible focus indicator on every focusable element: a 2px outline with 2px offset in `--color-accent`. `outline: none` without a replacement is forbidden. |
| A4 | Touch targets ≥ 44×44 CSS px (bottom-nav items ≥ 56px tall). |
| A5 | Dialogs trap focus, close on `Escape`, restore focus to the trigger, and use `role="dialog"` with `aria-labelledby` and `aria-modal="true"`. Radix provides this; it MUST NOT be overridden. |
| A6 | Every input has an associated `<label>`. Placeholders are never used as labels. |
| A7 | Icon-only buttons have `aria-label`. |
| A8 | Status information is never conveyed by colour alone — pinned notes show an icon, the active nav item shows a filled icon, error fields show text. |
| A9 | Route changes move focus to the `<h1>` and announce the new title via a visually hidden `aria-live="polite"` region. |
| A10 | A "Skip to content" link is the first focusable element. |
| A11 | `prefers-reduced-motion: reduce` disables all non-essential animation (§11.7). |
| A12 | Page zoom to 200% and text-only zoom to 200% cause no loss of content or function; no horizontal scrolling below 320px width. |
| A13 | `<html lang="en">` is set. |
| A14 | Loading regions use `aria-busy`; skeletons are `aria-hidden` with an accompanying visually hidden "Loading…". |
| A15 | The tile grid is a `<ul>` of `<li>` elements; tiles are `<article>` with `aria-labelledby` pointing at their heading. |

`eslint-plugin-jsx-a11y` MUST run with its `recommended` config as errors, and the Playwright suite MUST include `@axe-core/playwright` scans of the dashboard, notes list, note detail, settings, and login, failing on any serious or critical violation.

---

## 22. Performance budgets

| Metric | Budget | Measured |
|---|---|---|
| Initial JS (gzip) | ≤ 200 KB | `vite build` report, CI-enforced |
| Initial CSS (gzip) | ≤ 30 KB | as above |
| Largest route chunk (gzip) | ≤ 80 KB | as above |
| Largest Contentful Paint | ≤ 2.0s on simulated Fast 3G / 4× CPU throttle | Lighthouse CI |
| Cumulative Layout Shift | ≤ 0.05 | Lighthouse CI |
| Interaction to Next Paint | ≤ 200ms | Lighthouse CI |
| Lighthouse PWA category | Installable, all checks pass | Lighthouse CI |

Techniques that are **required**, not optional: route-level code splitting; `React.lazy` for dialogs heavier than 10 KB; tree-shakeable `lucide-react` imports (named, never the barrel); no source maps in the production bundle (generate them, upload them nowhere, do not serve them).

Techniques that are **forbidden** because they cost more than they return here: virtualised lists (page sizes are ≤100), prefetching every route on idle, and any runtime CSS-in-JS.

---

## 23. Testing requirements

### 23.1 Layers

| Layer | Tool | Scope |
|---|---|---|
| Unit | Vitest | Pure logic: `schemaToZod`, `href` translation, problem parsing, format helpers, refresh single-flight |
| Component | Vitest + RTL + MSW | Components in isolation against mocked HTTP |
| E2E | Playwright | Full stack against a real backend and database |

Coverage: ≥ 80% lines overall; ≥ 95% for `src/auth/` and `src/components/schema-form/`. The build fails below either.

### 23.2 Mocking

MSW handlers MUST be generated from the same `openapi.json` types so a mock cannot drift from the contract. A handler returning a shape that fails the generated type is a compile error.

### 23.3 Required test cases

**Auth**
1. Bootstrap: successful refresh yields `authenticated` and never renders the login screen.
2. Bootstrap: `401` yields `anonymous` and redirects a guarded route to `/login?next=…`.
3. Bootstrap: `auth.refresh_token_reused` yields `revoked` and renders the security banner.
4. Login success stores the token in memory and navigates to `next`.
5. `next` containing an absolute URL is ignored; navigation goes to `/`.
6. Login `401` shows one generic error identical for both failure modes.
7. Login `429` disables submit and counts down.
8. Three concurrent `401`s trigger exactly **one** refresh request and all three originals are replayed.
9. A `401` on `/auth/refresh` itself does not recurse.
10. A request already retried once is not retried again.
11. Explicit logout calls the endpoint, clears the query cache, and purges `/api/` cache entries.
12. **No credential reaches persistent storage:** after a full login flow, `localStorage`, `sessionStorage`, and all Cache Storage entries contain neither the access token nor the password.
13. Proactive refresh fires at `expires_in - 60s`.
14. Returning to visibility with an expired token refreshes before issuing other requests.

**Tiles**
15. The grid orders tiles by `order` then `key`.
16. An unknown `size` falls back to `medium`.
17. A tile with `count: 0` renders "0".
18. A tile with no items renders `empty_text` and still renders actions.
19. More than five items renders five plus "+N more".
20. An action without `body_schema` fires immediately; a `DELETE` action confirms first.
21. An action with `body_schema` opens a dialog whose fields match the schema.
22. A successful action invalidates the tile and the domain-derived query key.
23. A failing action keeps the dialog open with an inline error and preserved input.
24. One tile's request failing renders `TileError` for that tile only; siblings still render.
25. `done` renders a disabled checkbox and firing a click changes nothing.
26. `href` translation maps `/api/notes/x` to `/notes/x`; an unmapped path renders as text.
27. **No file in `src/components/tiles/` contains a string literal matching a known module domain** — asserted by a source scan test.

**Schema form**
28. String, number, integer, boolean, enum, array-of-string, and nested object each render the widget in Appendix B.
29. `required` fields are marked and block submit when empty.
30. An unsupported construct renders disabled with the fallback message and does not crash.
31. A secret field with value `"***"` renders empty with the "Saved" badge and is omitted from the payload when untouched.
32. A secret field cleared via the Clear button sends `null`.
33. Only changed keys appear in the `PUT` payload.
34. `422` errors map to the right fields; an unmapped error surfaces at form level.

**Notes**
35. List renders, searches with debounce, and reflects `q` in the URL.
36. Pin toggle is optimistic and rolls back on error.
37. Delete removes the row optimistically and restores it on error.
38. Create from the dialog invalidates the list and the notes tile.
39. Detail renders the body as plain text — an input containing `<script>` and Markdown syntax renders literally.
40. `404` on detail renders the not-found screen, not a toast.
41. Share `404 notes.user_not_found` maps to the email field.

**Offline and PWA**
42. With `navigator.onLine === false`, the banner appears and mutating controls are disabled.
43. Cached list data renders offline with the "Showing saved data" label.
44. A mutation attempted offline is blocked in the UI and issues no request.
45. The service worker precaches the shell and never caches `/api/auth/*`.
46. A waiting service worker shows the update toast and does not auto-reload.

**Accessibility**
47. Axe scans of five key screens report no serious or critical violations, in both themes.
48. A full keyboard traversal of the dashboard reaches every interactive element in DOM order.
49. Dialogs trap and restore focus.

### 23.4 E2E environment

Playwright runs against `docker compose -f docker-compose.yml -f docker-compose.e2e.yml up`, with a seeded admin and three notes. Tests MUST NOT depend on data they did not create. Each spec creates and cleans up its own fixtures via the API, not the UI.

---

## 24. Build, configuration, and deployment

### 24.1 Configuration

There is none at runtime. The API is at `/api` on the same origin (§2.1). The only build-time values are those Vite injects automatically (`import.meta.env.MODE`, `import.meta.env.DEV`) plus `__APP_VERSION__`, defined in `vite.config.ts` from `package.json`.

The implementer MUST NOT add a `VITE_API_URL`, a `config.json` fetch, or any other runtime configuration mechanism.

### 24.2 Scripts

```json
{
  "dev":          "vite",
  "build":        "tsc -b && vite build",
  "preview":      "vite preview",
  "test":         "vitest run --coverage",
  "test:watch":   "vitest",
  "test:e2e":     "playwright test",
  "lint":         "eslint . && prettier --check .",
  "fmt":          "eslint . --fix && prettier --write .",
  "typecheck":    "tsc -b --noEmit",
  "api:generate": "openapi-ts",
  "api:check":    "openapi-ts && git diff --exit-code src/api/generated"
}
```

### 24.3 Container

A two-stage Dockerfile at `clients/web/Dockerfile`: stage one runs `pnpm install --frozen-lockfile` and `pnpm build`; stage two is `nginx:1.27-alpine` serving `/usr/share/nginx/html`.

The nginx config MUST:
- Serve `index.html` for any path that does not match a file (SPA fallback), **excluding** `/api`.
- Set `Cache-Control: public, max-age=31536000, immutable` for `/assets/*` (content-hashed).
- Set `Cache-Control: no-cache` for `index.html`, `sw.js`, and `manifest.webmanifest` — a cached service worker or shell is how a PWA gets stuck on an old version.
- Set security headers: `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: geolocation=(), microphone=(), camera=()`, and a CSP of `default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`.
- Enable gzip and, where available, brotli for text assets.
- Run as non-root.

`'unsafe-inline'` in `style-src` is required by Radix's inline positioning styles; it is scoped to styles only and is not extended to scripts. The theme bootstrap script in `index.html` (§11.3) MUST therefore carry a build-time nonce or be moved to an external hashed file — the implementer MUST choose the external file to keep the CSP static.

### 24.4 Compose and routing

Add to the root `docker-compose.yml`:

```yaml
  web:
    build: ./clients/web
    restart: unless-stopped
    labels:
      - traefik.enable=true
      - traefik.http.routers.mystuff-web.rule=Host(`${PUBLIC_HOST}`)
      - traefik.http.routers.mystuff-web.priority=1
      - traefik.http.routers.mystuff-web.tls.certresolver=le
      - traefik.http.services.mystuff-web.loadbalancer.server.port=80
```

and amend the existing `api` service's router so it wins for API paths:

```yaml
      - traefik.http.routers.mystuff.rule=Host(`${PUBLIC_HOST}`) && (PathPrefix(`/api`) || PathPrefix(`/health`) || PathPrefix(`/openapi.json`))
      - traefik.http.routers.mystuff.priority=10
```

Priority is what makes same-origin work. The implementer MUST verify that `/api/auth/login` reaches the API and `/notes` reaches the web container.

---

## 25. Acceptance criteria

**Build and deploy**
1. `pnpm install && pnpm build` succeeds from a clean checkout with no backend running.
2. `pnpm api:check` passes, proving the committed client matches `openapi.json`.
3. `docker compose up -d` serves the app at `https://<host>/` with the API at `/api`, no CORS headers involved anywhere.
4. `pnpm lint`, `pnpm typecheck`, and `pnpm test` all pass; coverage gates in §23.1 are met.

**Auth**
5. Signing in, closing the tab, and reopening restores the session without re-entering a password.
6. After a full login, no credential is present in `localStorage`, `sessionStorage`, or Cache Storage (test 12).
7. Three simultaneous expired-token requests produce exactly one refresh call.
8. Token reuse produces the security banner and a signed-out state, not a silent redirect.
9. Signing out purges cached API responses; navigating back does not reveal the previous user's notes.

**Generic rendering**
10. The dashboard renders every tile in the manifest with no per-module client code; a source scan (test 27) confirms no module domain string appears in `src/components/tiles/`.
11. Adding a hypothetical module to the manifest (asserted with a mocked manifest containing an unknown domain and tile) renders its tile correctly, including an action dialog generated from its `body_schema`.
12. A settings panel renders from JSON Schema alone, including a secret field that round-trips without ever sending `"***"`.
13. An unsupported schema construct renders disabled rather than crashing.

**Notes**
14. Full CRUD, search, pin, and share work end to end against the real backend.
15. A note body containing HTML and Markdown renders literally as text.

**PWA and offline**
16. Lighthouse reports the app as installable with all PWA checks passing.
17. Installed on Android and desktop Chromium, the app launches standalone with correct icons and theme colour.
18. On iOS Safari the app is addable to the home screen, launches without browser chrome, and its bottom navigation clears the home indicator.
19. Going offline shows the banner, keeps cached views readable, disables mutations, and recovers on reconnect without a reload.
20. A new deploy surfaces the update toast; the app does not auto-reload.

**Quality**
21. Axe scans of the five key screens report no serious or critical violations in either theme.
22. All performance budgets in §22 are met in CI.
23. The app is fully usable at 320px width and at 200% zoom.
24. No `TODO`, `FIXME`, or commented-out code remains; no `console.log` outside error boundaries.

---

## 26. Out of scope

The implementer MUST NOT build: web push or the Notification API; background sync or an offline write queue; a Markdown or rich-text editor; file or image attachments; screens for any module other than `notes`; a note-sharing management view (no API exists); user administration beyond invites; audit-log views; telemetry, analytics, or error-reporting integrations; internationalisation; a settings UI for global (non-user-scoped) settings; drag-and-drop tile reordering (tile order is server-controlled by design).

Adding any of these is a specification violation.

---

## Appendix A — Query key registry

Keys are defined once in `src/api/queryKeys.ts`; ad-hoc key literals elsewhere are forbidden.

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

---

## Appendix B — JSON Schema to widget mapping

The backend emits Pydantic-generated JSON Schema. This table is exhaustive; anything absent renders as the disabled fallback (§14.3 rule 5).

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
| `{"type":"array","items":{"type":"string"}}` | Repeatable text rows with Add/Remove | `z.array(z.string())` |
| `{"type":"array","items":{"type":"object"}}` | Repeatable field group with Add/Remove | `z.array(z.object({…}))` |
| `{"type":"object","properties":{…}}` | Nested fieldset with a legend | `z.object({…})` |
| `{"anyOf":[X,{"type":"null"}]}` | Widget for X, marked optional | `X.nullable()` |
| `{"$ref":"#/$defs/X"}` | Resolve and recurse | resolved |
| anything else | Disabled fallback field | `z.unknown()` |

Constraints honoured: `minLength`, `maxLength`, `pattern`, `minimum`, `maximum`, `minItems`, `maxItems`, `required`, `default`, `title`, `description`. Nesting deeper than three levels renders the fallback — the backend is not expected to emit it.

---

## Appendix C — Design tokens

```css
:root {
  --radius-sm: 6px;  --radius-md: 10px; --radius-lg: 16px;
  --shadow-overlay: 0 8px 24px -4px rgb(0 0 0 / 0.16);
  --duration-fast: 120ms; --duration-slow: 200ms;
  --easing: cubic-bezier(0.2, 0, 0, 1);
  --font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
               "Helvetica Neue", Arial, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
}

[data-theme="light"] {
  --color-surface:        #ffffff;
  --color-surface-raised: #f7f7f8;
  --color-surface-sunken: #efeff1;
  --color-text:           #16181d;
  --color-text-muted:     #63666e;
  --color-border:         #dcdde1;
  --color-border-strong:  #b9bbc2;
  --color-accent:         #2f5fd0;
  --color-accent-text:    #ffffff;
  --color-danger:         #c02636;
  --color-success:        #1c7a4a;
  --color-warning:        #8a5a00;
}

[data-theme="dark"] {
  --color-surface:        #131519;
  --color-surface-raised: #1b1e24;
  --color-surface-sunken: #0e1013;
  --color-text:           #e8e9ec;
  --color-text-muted:     #9a9da6;
  --color-border:         #2a2e36;
  --color-border-strong:  #414651;
  --color-accent:         #7ba0f0;
  --color-accent-text:    #0e1013;
  --color-danger:         #f0808c;
  --color-success:        #5cc48d;
  --color-warning:        #e0b155;
}
```

All pairs above meet the contrast requirements in §21 A1; the implementer MUST verify with an automated contrast check rather than assuming.

---

## Appendix D — Copy strings

Copy is centralised in `src/lib/copy.ts` so tone stays consistent and future translation is possible.

| Context | String |
|---|---|
| Login error | "That email and password don't match. Please try again." |
| Account disabled | "This account has been deactivated. Contact your administrator." |
| No password reset | "Forgot your password? Ask your administrator to reset it." |
| Token reuse banner | "You were signed out because your session token was used twice. If this wasn't you, change your password now." |
| Invite expired | "This invitation has expired. Ask for a new one." |
| Invite used | "This invitation has already been used. Try signing in instead." |
| Invite not found | "We couldn't find that invitation. Check the link and try again." |
| Offline banner | "You're offline. You can read saved data, but changes won't save." |
| Cached-data label | "Showing saved data" |
| Update available | "A new version is available." |
| Server error toast | "Something went wrong on the server. Reference: {request_id}" |
| Permission denied | "You don't have permission to do that." |
| Settings decryption failed | "This setting can't be read — the server's encryption key may have changed. Contact your administrator." |
| Empty dashboard | "No tiles yet. Modules add tiles here once they're installed." |
| Empty notes | "No notes yet. Your first one is a click away." |
| Empty filtered notes | "No notes match your search." |
| Tile read-only checkbox | "Read-only in this version" |
| Share dialog note | "Sharing is additive — this list shows who you're adding, not who already has access." |
| PAT created warning | "Copy this token now. You won't be able to see it again." |
| Invite created note | "Send this link to the person yourself — MyStuff doesn't send email." |
