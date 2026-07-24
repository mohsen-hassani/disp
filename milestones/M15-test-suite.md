# M15 — Full test suite + coverage gates

**Status:** Complete

**Scope:** `tests/conftest.py` (session-scoped testcontainers Postgres, per-test transaction rollback), `tests/factories.py`, remaining tests for all 61 numbered cases in §22.3, the plug-in-proof test (§22.4), CLI tests via `ASGITransport`. Run `./dev test` to ≥85% overall / ≥95% on `core/auth/`.

Covers TECHNICAL-SPEC.md §22 (Testing requirements) in full.

---

## §22.2 Coverage

Overall line coverage ≥ 85%. `src/disp/core/auth/` ≥ 95%. The build fails below either threshold.

## §22.3 Required test cases

**Auth**
1. Password hash/verify round-trip; `verify_password` returns `False` for a malformed hash.
2. Policy rejects: < 12 chars, > 128 chars, password equal to email, a common-list password.
3. Login succeeds and sets a cookie with the correct attributes.
4. Login with unknown email and login with wrong password return byte-identical bodies (modulo `request_id`) and both `401`.
5. Login on a disabled account returns `403`.
6. Refresh rotates: new access token issued, new cookie set, old refresh token now rejected.
7. Refresh replay of a rotated token returns `401 auth.refresh_token_reused` **and** every session in the family has `revoked_at` set.
8. Refresh without `X-Requested-With` returns `403`.
9. Expired refresh token returns `401 auth.refresh_token_expired`.
10. Logout revokes the family and clears the cookie; a second logout still returns `204`.
11. PAT creation returns plaintext once; the same value never appears in the list response.
12. A PAT authenticates a normal endpoint successfully.
13. A PAT is rejected by `POST /api/auth/tokens` with `403 auth.pat_cannot_mint`.
14. A PAT is rejected by `POST /api/auth/password`.
15. A revoked PAT returns `401`; an expired PAT returns `401`.
16. `last_used_at` updates on first use and does not update again within 60 seconds.
17. `current_user` returns an equivalent `CurrentUser` (excluding `auth_method`) for a JWT and a PAT belonging to the same user.
18. Missing, malformed, and garbage `Authorization` headers each return the documented `401` code.
19. Invite create → accept → login works; the token is single-use (second accept returns `409`).
20. An expired invite returns `410`.
21. A second pending invite for the same email returns `409`.
22. Non-admin invite creation returns `403`.
23. Password change revokes other sessions but not the caller's.

**ACL**
24. `can` honours the rank ladder (read < write < owner) for each action.
25. Absence of a grant denies.
26. `can` with an unknown action raises `ValueError`.
27. An admin has no implicit access to another user's resource.
28. `readable_ids` returns owned and shared ids and nothing else.

**Registry**
29. Discovery loads `notes` and exposes it in the manifest.
30. A fixture module with a domain/package-name mismatch is fatal.
31. Duplicate tile keys across two fixture modules are fatal.
32. A missing dependency is fatal.
33. A dependency cycle is fatal and the message names both modules.
34. `MYSTUFF_MODULES` restricts loading; naming a non-existent module is fatal.

**Events**
35. A subscribed handler receives a published event.
36. A raising handler is logged and does not prevent the next handler from running; `publish` returns one `HandlerFailure`.
37. `publish_after_commit` dispatches only after commit and not after rollback.

**Notifier**
38. `send` with an unknown notification type raises `ValueError`.
39. Delivery with no configured channels writes `status='no_channels'` and does not raise.
40. Delivery calls Apprise with the decrypted URLs and logs `status='sent'`.
41. Apprise URLs never appear in captured logs.

**Settings**
42. Secret round-trip encrypts at rest (`value_encrypted` non-null, `value_json` null) and decrypts correctly.
43. `get_all` masks secrets by default and reveals them only when asked.
44. A wrong key raises `SettingsDecryptionError`.

**Notes**
45. Create returns `201`, persists to `notes.notes`, creates an OWNER ACL row, and emits `NoteCreated` (assert the handler ran).
46. List excludes soft-deleted notes and another user's notes.
47. Reading another user's note returns `404`.
48. Share with `read` lets the grantee read but not update (update returns `403`).
49. Full-text search matches on title and body.
50. Pagination returns a stable, non-overlapping sequence across pages.
51. `purge_deleted` removes only rows deleted more than 30 days ago.

**Platform**
52. `GET /health` returns `ok` with a live database.
53. `GET /api/dashboard/tiles` renders the notes tile; a provider that raises yields the fallback tile rather than a `500`.
54. `GET /api/dashboard/tiles/{unknown}` returns `404`.
55. Every route in the OpenAPI document has a unique `operation_id`.
56. `oidc.resolve_external_token` raises `NotImplementedError`.

**CLI** (against the ASGI app via a transport-injected client)
57. `disp login` writes a `0600` config containing a PAT and no password.
58. A config file with mode `0644` is refused with exit `3`.
59. `disp notes add` from piped stdin creates a note.
60. `--json` output parses as JSON and contains no ANSI escapes.
61. A `401` from the server exits `3` with a "run `disp login`" message.

## §22.4 The plug-in proof

`tests/fixtures_modules/hello/` MUST contain a minimal module (manifest, one tile returning a static `TileData`, no router, no DB). A test MUST:

1. Copy or path-inject it so discovery finds it.
2. Restart the app factory.
3. Assert it appears in `GET /api/dashboard/manifest` and its tile renders in `GET /api/dashboard/tiles`.
4. Assert via `git diff --name-only` (or an equivalent recorded file list) that **no file under `src/disp/core/` was modified** to make this work.

## §22.5 The boundary test

Already implemented and verified at M6 (`tests/core/test_boundaries.py`) — re-run here as part of the full suite, now with `modules/notes/` populated (M13) giving it real, non-vacuous content to check.

## Notes

- `tests/conftest.py` needs to set required `MYSTUFF_*` env vars (via `monkeypatch.setenv` or a `.env.test`) **before** any test module imports `disp.core.scheduler` (or anything importing it transitively, e.g. `disp.core.app`) — see M7's note on that module's import-time singleton construction.
- Time-dependent tests (refresh expiry, invite expiry, `last_used_at`'s 60-second rule) use `freezegun` or explicit injected `now`, never `sleep`, per §22.1.

## Implementation notes

**Final numbers:** `./dev test` → 133 tests passed, 86.5% overall line coverage (gate: ≥85%),
98% on `src/disp/core/auth/` (gate: ≥95%). `./dev lint` (ruff check + format + mypy) is clean.

### Infrastructure (`tests/conftest.py`)

- A single `testcontainers.postgres.PostgresContainer("postgres:16", driver="asyncpg")` starts at
  **module import time** (not inside a pytest fixture) — a fixture would run too late, since
  `disp.core.scheduler` builds a `procrastinate.App` bound to `MYSTUFF_DATABASE_URL_SYNC` at
  *import time* (M7), and the first test module to import anything that pulls in
  `disp.core.scheduler` does so during pytest's collection phase, which runs immediately after
  conftest.py finishes executing top-to-bottom.
- Migrations (`alembic --name=core`, `--name=notes`) and `procrastinate schema --apply` run once,
  via `subprocess`, against the container, before any fixture exists.
- Per-test isolation: `db_connection` opens one connection + one outer transaction per test;
  `session_maker` builds sessions bound to that connection via
  `join_transaction_mode="create_savepoint"`, so an internal `session.commit()` (e.g. inside an
  overridden `get_session`) only releases a savepoint, keeping the outer transaction — and
  `db_connection`'s rollback at teardown — intact.
- `app` is **session-scoped**, not per-test: `disp.core.scheduler.app` is a process-wide
  procrastinate singleton, and `create_app()` registers each module's scheduled tasks onto it by
  name — a second `create_app()` call in the same process raises `SchedulerRegistrationError`
  (duplicate task name). So the FastAPI app is built exactly once; only the session behind
  `get_session` varies per test (`client` fixture swaps `app.dependency_overrides[get_session]` to
  yield that test's `db_session`, mirroring `get_session`'s own commit/rollback semantics).
- `client` is an `httpx.AsyncClient` over `httpx.ASGITransport(app=app)`, per §22.1.

### Bugs found and fixed while writing this milestone

1. **`main_callback()`'s config-error path bypassed the §19.3 exit-code mapping.** The CLI's root
   Typer callback calls `cli_config.default_profile_name()` unconditionally (to resolve `--profile`
   when omitted) — this happens *before* any `@handle_cli_errors`-wrapped command body runs, so a
   `ConfigCliError` there (e.g. a `0644` config file) propagated as an unhandled exception instead
   of the documented exit code 3. Fixed in `src/disp/cli/main.py` by wrapping that one call in its
   own `try/except CliError`, mirroring `handle_cli_errors`'s own logic. Caught by writing §25 item
   28's exit-code test (a `0644` config file) as an actual `CliRunner` invocation rather than a
   unit test of `_check_permissions()` in isolation.

2. **`disp notes list --json`'s trailing-flag JSON envelope was a bare array, not `{"items": [...]}`**
   — actually caught and fixed during M14, re-verified here as part of §25 item 27's literal
   acceptance command (`disp notes list --json | jq '.items[0].id'`).

3. **coverage.py silently drops most post-`await` lines in SQLAlchemy-async code** unless
   configured for it. SQLAlchemy's asyncio extension bridges to asyncpg via `greenlet_spawn`;
   coverage's default tracer isn't greenlet-aware, so any line *after* an `await
   session.execute(...)` (i.e. almost the entire body of most route handlers) was silently
   reported as "missing" even when directly proven to execute (verified with a temporary debug
   `print()` inside `change_password` that fired on every test run, while coverage still listed
   its lines as uncovered). This made `auth/routes.py` read as 57–58% covered regardless of how
   thoroughly it was tested. Fixed with `concurrency = ["greenlet", "thread"]` in
   `[tool.coverage.run]` (`pyproject.toml`) — auth/routes.py immediately jumped to 84%, and overall
   coverage from 78% to 84% in the same test run with zero new tests. This is a general hazard for
   any FastAPI+SQLAlchemy-async project measuring coverage, not specific to this codebase.

4. **`./dev test` and a bare `pytest` invocation silently ran with different settings**, because
   `./dev` sources the repo's own `.env` (dev defaults: `MYSTUFF_ENV=development`,
   `MYSTUFF_RATE_LIMIT_ENABLED=true`, a database URL pointed at the persistent dev Postgres) into
   the shell *before* invoking `uv run pytest`, while a bare `pytest` invocation never sees `.env`
   at all. `tests/conftest.py` used `os.environ.setdefault(...)` for its required overrides, which
   only takes effect when the variable is *not already set* — so under `./dev test`, real rate
   limiting silently applied across the whole suite (most tests share `DEFAULT_PASSWORD`-driven
   logins that easily exceed 5/minute-per-email once dozens of tests run in ~10 seconds), producing
   24 failures that never reproduced when running `pytest tests/` directly. Fixed by making every
   one of conftest's required env vars an **unconditional** assignment
   (`os.environ["KEY"] = value`, not `setdefault`) — tests must be hermetic regardless of the
   invoking shell's environment. This is the reason `./dev test`'s own gate command is the one
   that matters; a plain `pytest` run passing is not sufficient proof by itself.

5. **Testing the CLI's synchronous `httpx.Client` against the async ASGI app requires a
   long-lived portal, not `starlette.testclient.TestClient(app)._transport` directly.** The CLI's
   `ApiClient` is deliberately synchronous (Typer commands aren't async), so bridging it to the
   async app needs a background thread ("portal") running its own event loop. Unless
   `TestClient` is entered as a context manager, its `_portal_factory` spins up a *brand new*
   portal (and event loop) for every single request and tears it down immediately after — so a
   second request over the same transport hit "Event loop is closed" (an asyncpg connection bound
   to the first, now-dead, loop). Entering `TestClient` as a context manager isn't an option either,
   since that re-runs the ASGI lifespan a second time on an app the session-scoped `app` fixture
   already started. Fixed in `tests/cli/conftest.py`'s `cli_transport` fixture by building the
   lower-level `starlette.testclient._TestClientTransport` directly, with a `portal_factory` that
   always returns the SAME portal (opened once per test, closed at teardown). Required adding an
   optional `transport: httpx.BaseTransport | None = None` parameter to `ApiClient.__init__`
   (`src/disp/cli/client.py`) as a testing seam — normal CLI usage never passes it.

6. **The CLI's own request-serving session can't share `db_session` at all**, for the same
   loop-affinity reason as #5: even with a stable portal, its thread runs a different event loop
   than the main test session's. So CLI tests seed data through a *separate*, real-commit session
   (`cli_db` fixture, bound to its own engine, never touched from the portal thread) rather than
   the per-test-rollback `db_session`, and `get_session` is overridden (only for the `cli_env`
   fixture's duration) to build sessions from yet another engine — one whose connections are opened
   lazily, on first use, from *within* the portal thread, so they consistently bind to its loop
   rather than the main one. Both engines point at the same testcontainers Postgres, so writes
   from one are visible to the other via ordinary commit/read-committed semantics.

7. **Real-commit CLI test data isn't rolled back, and other tests need to account for that.**
   `notes_purge_deleted`'s own test originally asserted `select(Note.id)` (no filter) equalled
   exactly its own two expected rows — this passed in isolation but failed intermittently as part
   of the full suite, because a CLI test (§25 item 26, "`disp notes add` from piped stdin creates
   a note") had already committed one real, permanent note to the same container via its own
   real-commit session. Fixed by scoping the assertion to the specific note ids the test itself
   created (`Note.id.in_(all_ids)`), which is also the more realistic test shape regardless (a
   production `notes` table always holds other users' data too).
   `test_seed_admin_creates_first_admin_user` (disp-admin's "refuse if any user exists" check has
   no scoping at all) hit the same issue and is fixed the same way: it clears `core.users` itself
   before asserting the "empty table" branch, since no other test depends on a specific committed
   user surviving across test *files*.

8. **`seed_admin()` calls `asyncio.run()` internally**, which cannot run from within
   pytest-asyncio's already-active session loop — `tests/core/test_cli_admin.py`'s tests are
   therefore plain sync functions, with setup/verification done through a raw `psycopg` connection
   rather than the async `db_session` fixture.

9. **Rate-limit tests must never touch `get_settings.cache_clear()` mid-suite.** The first attempt
   toggled `MYSTUFF_RATE_LIMIT_ENABLED` via `monkeypatch.setenv` + `get_settings.cache_clear()`
   (the same pattern `test_registry.py` uses for `MYSTUFF_MODULES`), which is safe there because
   nothing else depends on settings staying constructed mid-test. For rate limiting it reintroduced
   exactly the ordering hazard from #4 across the *whole rest of the suite*. Fixed by mutating the
   attribute directly on the already-cached `Settings` singleton
   (`monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)`), which `monkeypatch` reverts
   after the test without ever invalidating or rebuilding the shared cached instance.

### Coverage gate notes

`src/disp/worker.py` and `src/disp/main.py` (94 combined statements, 0% covered) are the two
process entrypoints. Both are structurally hard to exercise in this test session:
`worker.py`'s `_build_platform()` calls `registry.wire(None, platform)`, which would register
`notes.purge_deleted` on the same procrastinate singleton the session-scoped `app` fixture already
registered it on (`SchedulerRegistrationError`); `main.py`'s `app = create_app()` at import time
hits the same conflict the instant it's imported anywhere in this process. Both were left
uncovered rather than forcing an awkward, low-value workaround — the ≥85% gate is met comfortably
regardless (86.5%), and every function `_build_platform()`/`_run()` call into
(`create_engine`, `EventBus`, `SettingsStore`, `Registry.discover`/`wire`, `SchedulerFacade`) is
already covered via the app-fixture-based tests.
