# M12 — Bring up Postgres, first real DB run

**Status:** Complete

**Scope:** Start OrbStack/Docker, `./dev up`, `./dev migrate`, `procrastinate schema --apply`, run the full test suite accumulated so far (M1–M11) against a real Postgres 16 container, fix whatever breaks. This is the first milestone where any DB-touching code (M2, M5, M6's session/ACL queries, M8's settings persistence, M9's notification_log writes) gets exercised for real.

Covers TECHNICAL-SPEC.md §22.1 (testing infrastructure) and the operational parts of §7.3/§13.1.

---

## §22.1 Infrastructure

- `pytest` with `asyncio_mode = "auto"`.
- A real PostgreSQL 16 via `testcontainers`, started once per session. SQLite is forbidden.
- Per-test isolation: each test runs in a transaction that is rolled back at teardown. Tests that need committed data use a dedicated fixture that truncates afterwards.
- `httpx.ASGITransport` against the real app; no mocking of FastAPI internals.
- Apprise is mocked at the `apprise.Apprise.notify` boundary. No test performs outbound network I/O.
- Time-dependent tests use `freezegun` or explicit injected `now` parameters — never `sleep`.

## Relevant commands (§7.3, §13.1)

| Command | Effect |
|---|---|
| `./dev migrate` | Upgrade every branch to head, in order: `core`, then modules alphabetically |
| `./dev migrate core` | Upgrade only `core` |

- `procrastinate schema --apply` runs as part of `./dev migrate` and as a one-shot compose command, before the worker starts.

## Notes

- At this point in the build, `modules/notes/` doesn't exist yet (M13 comes after), so only the `core` alembic branch can actually be migrated and exercised — `./dev migrate core`, not the full `./dev migrate`.
- This is also the first point where `disp.core.scheduler`'s module-level `procrastinate.App` (which needs `MYSTUFF_DATABASE_URL_SYNC` to actually resolve a live Postgres) gets imported against a real, reachable database rather than a syntactically-valid-but-unreachable placeholder URL.
- Fix-forward here: any mismatch between the SQLAlchemy ORM models (M2) and hand-authored DDL (M5), or between assumed and actual library behavior (procrastinate 3.x, psycopg3 async mode, etc.), gets caught and corrected against a real server before more code is layered on top in M13+.

## Implementation notes

Docker/OrbStack wasn't running; started it (`open -a OrbStack`, waited for the daemon), then ran a plain `docker run postgres:16-alpine` container directly rather than `./dev up` (no `docker-compose.yml` yet — that's M16). Applied only the `core` alembic branch (`./dev migrate core`) plus `procrastinate schema --apply`, then did extensive live-fire verification beyond just re-running the existing (DB-agnostic) unit suite, since none of the M1–M11 tests actually touch a database. **Four real bugs were found and fixed**, all only reproducible against a live Postgres:

1. **`dev` script never loaded `.env` into the shell environment.** `alembic`/`procrastinate` (invoked via `uv run alembic ...`) read `MYSTUFF_DATABASE_URL_SYNC` straight from `os.environ` — a `.env` file on disk does nothing for them (only `pydantic-settings`, inside the app, reads `.env`). Fixed by adding `set -a; source .env; set +a` near the top of `dev`.
2. **`env.py` had no derivation fallback for `MYSTUFF_DATABASE_URL_SYNC`.** Unlike `Settings` (M1), which derives it from `MYSTUFF_DATABASE_URL` when unset, the Alembic `env.py` (M5) required it to be set explicitly. Added the same derivation logic to `env.py`'s `_database_url()` so a plain `.env` with only `MYSTUFF_DATABASE_URL` works for migrations too.
3. **Settings PUT handler crashed on any non-secret structured field** (`TypeError: Object of type ChannelConfig is not JSON serializable`). `TypeAdapter.validate_python()` returns live Pydantic model instances for fields like `list[ChannelConfig]`; `SettingsStore.set()` then tried to hand those straight to `json.dumps` for the JSONB column. Fixed by round-tripping through `TypeAdapter.dump_python(parsed, mode="json")` before storage, converting back to plain JSON-safe data.
4. **`ck_settings_one_value` violated on every plain (non-secret) settings write.** SQLAlchemy's `JSONB` type, by default, encodes a Python `None` as the JSON scalar `"null"` — a non-NULL JSONB value — rather than SQL `NULL`, so `value_json` was never actually NULL even when meant to be unset, tripping the `(value_json IS NULL) <> (value_encrypted IS NULL)` constraint. Fixed by declaring the column as `JSONB(none_as_null=True)` in `models.py`, which makes SQLAlchemy bind Python `None` as true SQL NULL for that column.

**End-to-end verification performed against the live database** (beyond the existing unit suite, which still passes unchanged): `disp-admin seed-admin` (create + correctly refuse-on-second-run); full HTTP flows via `TestClient` for login (right/wrong password), PAT creation/use, PAT-cannot-mint-PAT, PAT-cannot-change-password, CSRF-required-on-refresh, refresh rotation with a real cookie, and `/health` reporting `ok` against a live DB; **refresh-token reuse/replay detection** (rotate once, replay the old token → `401 auth.refresh_token_reused` with a `WARNING` log, confirmed both sessions in the family end up `revoked_at` set with the correct `revoked_reason`s, confirmed the *new* token is also rejected afterward); the **full invite lifecycle** (create → duplicate-pending 409 → existing-email 409 → list → weak-password 422 → accept 201 → second-accept 409 → non-admin-403); the **entire ACL layer** directly against the DB (rank ladder, unknown-action `ValueError`, no-implicit-ownership for admins, `readable_ids`, `list_grants`, `revoke`) since there's no `notes` module yet to exercise it through HTTP; the **notifier delivery task** with a real DB session and only Apprise mocked (per §22.1's boundary), confirming the encrypted URL round-trips correctly and never appears in the log line; and — the most complete integration check — **started the actual `python -m disp.worker` process**, deferred a `core.deliver_notification` job through `SchedulerFacade.defer()` from a separate process, and watched the worker pick it up from the Postgres-backed queue, attempt delivery (to a deliberately-unreachable URL), write `notification_log` rows on every attempt, and retry three times at the configured ~10s backoff before Procrastinate marked the job `failed` at 4 total attempts — confirming the two-process architecture (§2's diagram) actually works end to end, not just in-process.

Final state: dev Postgres container left running (`disp-postgres-dev`), test data wiped, one clean admin re-seeded (`dev@example.com`) for ongoing local development. `ruff`/`ruff format --check`/`mypy` all clean; the pre-existing 23-test suite still passes unchanged.
