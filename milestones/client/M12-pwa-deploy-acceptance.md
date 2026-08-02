# M12 — Performance, deployment, and acceptance sweep

**Status:** Not started

**Scope:** `clients/web/Dockerfile`, `clients/web/nginx.conf` (or equivalent), amendments to the
root `docker-compose.yml` (new `web` service + `api` service's router-priority amendment), Lighthouse
CI config.

Covers TECHNICAL-SPEC-WEB.md §22 (Performance budgets), §24.3–24.4 (Container, Compose and routing),
§25 (Acceptance criteria) — the closing milestone, mirroring `milestones/M16-deployment-docs.md`'s
role for the backend.

---

## §22. Performance budgets

| Metric | Budget | Measured |
|---|---|---|
| Initial JS (gzip) | ≤200 KB | `vite build` report, CI-enforced |
| Initial CSS (gzip) | ≤30 KB | as above |
| Largest route chunk (gzip) | ≤80 KB | as above |
| Largest Contentful Paint | ≤2.0s (simulated Fast 3G / 4× CPU) | Lighthouse CI |
| Cumulative Layout Shift | ≤0.05 | Lighthouse CI |
| Interaction to Next Paint | ≤200ms | Lighthouse CI |
| Lighthouse PWA category | Installable, all checks pass | Lighthouse CI |

**Required techniques**: route-level code splitting (M04 already builds routes as lazy chunks —
verify the budget is actually met, don't just trust the intent), `React.lazy` for dialogs >10KB
(M05's `TileActionDialog`, M06's `SchemaForm` widgets, M07/M08's create/share dialogs are candidates
— audit which ones actually exceed 10KB before lazy-loading everything reflexively), tree-shakeable
named `lucide-react` imports (never the barrel import — grep for `from 'lucide-react'` without
destructured named imports across the whole `src/` tree), no source maps in the production bundle
(generate for local debugging, upload nowhere, don't serve them).

**Forbidden**: virtualized lists (page sizes are ≤100 throughout, per every list milestone — M08's
notes list included), prefetching every route on idle, any runtime CSS-in-JS.

If the budget is blown, the fix is almost always cutting an unnecessary dependency or un-lazifying
something eagerly bundled — not raising the budget number. Treat these as hard gates the same way
the backend's coverage percentages are hard gates, not targets to negotiate down when inconvenient.

## §24.3 Container

Two-stage `clients/web/Dockerfile`: stage one `pnpm install --frozen-lockfile` + `pnpm build`; stage
two `nginx:1.27-alpine` serving `/usr/share/nginx/html`. This mirrors the root `Dockerfile`'s own
multi-stage discipline (`CLAUDE.md`'s Docker section: matching `WORKDIR` between builder and runtime
stages, `--no-editable`-equivalent hygiene) even though the failure modes are different for a static
build — **verify by actually running the built image**, not just building it, the same lesson the
backend's own Dockerfile milestone learned the hard way (`CLAUDE.md`: *"Both were caught by actually
running the built image, not just building it — always verify a Dockerfile change by running the
image, not just building it."*).

nginx config MUST:
- Serve `index.html` for any path not matching a file (SPA fallback), **excluding** `/api`.
- `Cache-Control: public, max-age=31536000, immutable` for `/assets/*` (content-hashed).
- `Cache-Control: no-cache` for `index.html`, `sw.js`, `manifest.webmanifest` — a cached service
  worker or shell is precisely how a PWA gets stuck on a stale version; this is not a generic
  best-practice suggestion, it's load-bearing for M09's update flow to work at all.
- Security headers: `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`,
  `Permissions-Policy: geolocation=(), microphone=(), camera=()`, and CSP:
  `default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self';
  connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`.
- gzip and, where available, brotli for text assets.
- Run as non-root.

`'unsafe-inline'` in `style-src` is required by Radix's inline positioning styles (scoped to styles
only — not extended to `script-src`). **The theme-bootstrap script (M01) MUST be an external hashed
file, not inline** — M01 was already instructed to write it this way from the start specifically so
this milestone doesn't have to retrofit it under a CSP that has no `script-src 'unsafe-inline'`.
Verify that instruction was actually followed before finalizing this CSP — an inline `<script>` left
in `index.html` will silently fail under this exact policy, and the failure mode (no visible error,
just a flash-of-wrong-theme returning) is easy to miss in a quick smoke test.

## §24.4 Compose and routing

Add to the root `docker-compose.yml`:

```yaml
  web:
    build: ./clients/web
    restart: unless-stopped
    labels:
      - traefik.enable=true
      - traefik.http.routers.disp-web.rule=Host(`${PUBLIC_HOST}`)
      - traefik.http.routers.disp-web.priority=1
      - traefik.http.routers.disp-web.tls.certresolver=le
      - traefik.http.services.disp-web.loadbalancer.server.port=80
```

Amend the existing `api` service's router (confirmed today, `docker-compose.yml:31-34` —
`traefik.http.routers.disp`, service port `8000`, already named `disp` with **no** priority or
`PathPrefix` condition set, since it's currently the only web-facing service) so it wins for API
paths once `web` is added:

```yaml
      - traefik.http.routers.disp.rule=Host(`${PUBLIC_HOST}`) && (PathPrefix(`/api`) || PathPrefix(`/health`) || PathPrefix(`/openapi.json`))
      - traefik.http.routers.disp.priority=10
```

This is an **amendment to the existing `disp` router's `rule` label and a new `priority` label**,
not a rename — the router is already correctly named `disp`, confirming the same "disp is already
the real wire-level name" pattern found everywhere else in this codebase (M00's cookie/CSRF-header
findings, M00-bootstrap's console-script decision).

Priority is what makes same-origin work at all (§2.1's whole premise). **Verify** — don't just
configure — that `/api/auth/login` reaches the API container and `/notes` reaches the web container
once both services are up.

## §25. Acceptance criteria — the milestone's own definition of done

Every criterion below must be independently checked, not assumed from earlier milestones' own
"verification" sections passing in isolation — this is the first point where the whole system runs
together as Docker Compose would run it in production.

**Build and deploy**: (1) `pnpm install && pnpm build` succeeds from a clean checkout, no backend
running. (2) `pnpm api:check` passes. (3) `docker compose up -d` serves the app at
`https://<host>/` with the API at `/api`, zero CORS headers anywhere. (4) `pnpm lint`,
`pnpm typecheck`, `pnpm test` all pass, coverage gates met.

**Auth**: (5) sign in, close tab, reopen — session restored without re-entering a password. (6) no
credential in `localStorage`/`sessionStorage`/Cache Storage after login. (7) three simultaneous
expired-token requests → one refresh call. (8) token reuse → security banner + signed-out state, not
a silent redirect. (9) sign-out purges cached API responses; back navigation doesn't reveal the
previous user's notes.

**Generic rendering**: (10) dashboard renders every manifest tile with zero per-module client code;
source scan confirms it. (11) a hypothetical unknown-domain module (mocked manifest) renders
correctly, including an action dialog from its `body_schema`. (12) a settings panel renders from
JSON Schema alone, including a secret field round-tripping without ever sending `"***"`. (13) an
unsupported schema construct renders disabled, not crashing.

**Notes**: (14) full CRUD/search/pin/share against the real backend. (15) a note body with HTML and
Markdown renders literally as text.

**PWA and offline**: (16) Lighthouse reports installable, all PWA checks passing. (17) installed on
Android/desktop Chromium, launches standalone with correct icons/theme color. (18) iOS Safari:
addable to home screen, launches without browser chrome, bottom nav clears the home indicator. (19)
offline: banner, cached views readable, mutations disabled, recovers on reconnect without a reload.
(20) a new deploy surfaces the update toast; no auto-reload.

**Quality**: (21) axe scans of five key screens, no serious/critical violations, both themes. (22)
all §22 performance budgets met in CI. (23) fully usable at 320px width and 200% zoom. (24) no
`TODO`/`FIXME`/commented-out code; no `console.log` outside error boundaries.

## §26. Out of scope — confirm nothing here crept in

Web push/Notification API; background sync or offline write queue; a Markdown/rich-text editor;
file/image attachments; screens for any module other than `notes`; a note-sharing management view;
user administration beyond invites; audit-log views; telemetry/analytics/error-reporting of any
kind; internationalization; a global (non-user-scoped) settings UI; drag-and-drop tile reordering.
Grep the final `src/` tree for any of these before signing off — each would be a specification
violation per §26's own explicit framing, not a harmless bonus feature.

## Dependencies

Everything — **M00 through M11** must be complete. This is the final milestone in the sequence.

## Verification

- `docker compose build web && docker compose up -d` — actually run the built image, hit it in a
  browser, don't just confirm the build exits 0.
- Lighthouse CI run against the composed stack, all §22 budgets green.
- Full manual pass through the §25 acceptance-criteria list above, checking each item against the
  running system rather than trusting each origin milestone's own sign-off.
