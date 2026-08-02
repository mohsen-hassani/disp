# M11 — Test suite

**Status:** Not started

**Scope:** `clients/web/tests/{unit/,mocks/{handlers.ts,server.ts},e2e/{auth,dashboard,notes,
settings,pwa}.spec.ts}`, `clients/web/vitest.config.ts` and `clients/web/playwright.config.ts`
coverage/CI wiring (files created in M01, configured for real here).

Covers TECHNICAL-SPEC-WEB.md §23 (Testing requirements) in full — the complete enumerated test list
(cases 1–49) and coverage gates. Mirrors `milestones/M15-test-suite.md`'s role for the backend: the
milestone that proves everything built so far actually holds together, rather than introducing new
product surface.

---

## §23.1 Layers

| Layer | Tool | Scope |
|---|---|---|
| Unit | Vitest | Pure logic: `schemaToZod`, `href` translation, problem parsing, format helpers, refresh single-flight |
| Component | Vitest + RTL + MSW | Components in isolation against mocked HTTP |
| E2E | Playwright | Full stack against a real backend and database |

Coverage gates: **≥80% lines overall; ≥95% for `src/auth/` and `src/components/schema-form/`.** The
build fails below either threshold — treat this the same way the backend's own coverage gate
(`≥85% overall, ≥95% on src/disp/core/auth/`, per `CLAUDE.md`) is treated: a real gate, not
aspirational, and if a number looks implausibly low for code that's clearly well-tested, check the
coverage tool's config (the backend hit exactly this class of false-negative with
`concurrency = ["greenlet", "thread"]` — the client's async equivalent is less likely with
Vitest/V8 coverage, but don't assume; verify the number reflects reality before adding tests to
chase a number that might already be wrong for tooling reasons).

## §23.2 Mocking

MSW handlers **MUST be generated from the same `openapi.json` types** M02's SDK uses — a handler
returning a shape that fails the generated type is a compile error, not a runtime surprise. This is
what keeps the mock layer from drifting out of sync with the real contract silently; don't hand-type
response shapes in `tests/mocks/handlers.ts` even for convenience.

## §23.3 Complete required test list, mapped to the milestone that built the code under test

**Auth** (built in M03) — cases 1–14:
1. Bootstrap: successful refresh → `authenticated`, login screen never renders.
2. Bootstrap: `401` → `anonymous`, guarded route redirects to `/login?next=…`.
3. Bootstrap: `auth.refresh_token_reused` → `revoked`, security banner renders.
4. Login success stores token, navigates to `next`.
5. Absolute-URL `next` ignored; navigates to `/`.
6. Login `401` → one generic error, identical for both failure modes.
7. Login `429` disables submit, counts down.
8. Three concurrent `401`s → exactly one refresh request, all three replayed.
9. `401` on `/auth/refresh` itself doesn't recurse.
10. An already-retried-once request isn't retried again.
11. Explicit logout: calls endpoint, clears query cache, purges `/api/` cache entries.
12. No credential reaches persistent storage after a full login flow.
13. Proactive refresh fires at `expires_in - 60s`.
14. Return-to-visibility with an expired token refreshes before other requests.

**Tiles** (M05) — cases 15–27:
15. Grid orders by `order` then `key`. 16. Unknown `size` falls back to `medium`. 17. `count: 0`
renders "0". 18. No items → `empty_text` + actions still render. 19. >5 items → 5 + "+N more".
20. No-`body_schema` action fires immediately; `DELETE` confirms first. 21. `body_schema` action
opens a dialog matching the schema. 22. Successful action invalidates the tile + domain-derived key.
23. Failing action keeps the dialog open, inline error, preserved input. 24. One tile's failure
renders `TileError` only for that tile. 25. `done` renders disabled, click changes nothing.
26. `href` translation maps correctly; unmapped renders as text. 27. **Source-scan**: no file in
`src/components/tiles/` contains a known module-domain string literal.

**Schema form** (M06) — cases 28–34:
28. Each Appendix B widget renders correctly for its schema. 29. `required` fields marked, block
empty submit. 30. Unsupported construct renders disabled, doesn't crash. 31. `"***"` secret renders
empty with "Saved" badge, omitted from payload untouched. 32. Clear sends `null`. 33. Only changed
keys in the `PUT` payload. 34. `422` errors map to the right fields; unmapped → form-level.

**Notes** (M08) — cases 35–41:
35. List renders, debounced search, `q` reflected in URL. 36. Pin toggle optimistic, rolls back on
error. 37. Delete optimistic, restores on error. 38. Create invalidates list + tile. 39. Detail body
with `<script>`/Markdown renders literally as text. 40. `404` on detail → not-found screen, not a
toast. 41. Share `404 notes.user_not_found` → email field.

**Offline and PWA** (M09) — cases 42–46:
42. Offline: banner appears, mutating controls disabled. 43. Cached list data renders offline with
"Showing saved data". 44. Offline mutation attempt blocked in UI, issues no request. 45. Service
worker precaches shell, never caches `/api/auth/*`. 46. Waiting service worker shows update toast,
no auto-reload.

**Accessibility** (M10) — cases 47–49:
47. Axe scans of five key screens: no serious/critical violations, both themes. 48. Full keyboard
traversal of the dashboard reaches every interactive element in DOM order. 49. Dialogs trap and
restore focus.

Every case above should already have at least a unit/component-level test from its origin
milestone (M03/M05/M06/M08/M09/M10 each said so explicitly in their own Verification sections).
**This milestone's job is not to write all 49 from scratch** — it's to (a) promote the ones worth
running as full Playwright e2e against a real backend, (b) fill any gap where an earlier milestone's
test turned out to be missing or superficial, and (c) assemble the MSW handler set and coverage
tooling that ties them all together in CI.

## §23.4 E2E environment

Playwright runs against `docker compose -f docker-compose.yml -f docker-compose.e2e.yml up`
(`docker-compose.e2e.yml` is a new file this milestone creates — check `docker-compose.yml` and
`docker-compose.test.yml` for the existing compose-file conventions before writing it, per
`CLAUDE.md`'s note that these two existing files serve very different purposes and shouldn't be
confused), with a seeded admin and three notes (reuse the backend's existing `./dev seed` recipe —
`README.md`'s quickstart already documents "creates a dev admin user and three sample notes",
confirm it's invokable non-interactively for CI). Tests MUST NOT depend on data they didn't create —
each spec creates and cleans up its own fixtures via the API, not the UI, to keep specs independent
and fast.

## Dependencies

Runs after **M03–M10** — by design, this is the milestone that exercises everything built so far
against a real backend, so it can't meaningfully start earlier. **M00** must be complete (M06's
settings tests need real `schema`/`x-secret` data from a live backend, not just a hand-written
fixture, to count as true e2e coverage).

## Verification

- `pnpm test` (Vitest + coverage) passes with coverage ≥80% overall, ≥95% on `src/auth/` and
  `src/components/schema-form/`.
- `pnpm test:e2e` (Playwright, against `docker-compose.e2e.yml`) passes all 49 enumerated cases.
- CI runs `pnpm api:check` (M02) and fails on drift — confirms the committed generated client still
  matches a freshly-generated `openapi.json` from the current backend.
