# M11 — cli_admin.py (disp-admin seed-admin)

**Status:** Complete

**Scope:** `disp-admin seed-admin --email <e> --display-name <n>`.

Covers TECHNICAL-SPEC.md §10.11 (Admin bootstrap).

---

## §10.11 Admin bootstrap

`disp-admin seed-admin --email <e> --display-name <n>` MUST create the first admin. The password is read from the `MYSTUFF_SEED_PASSWORD` environment variable, or generated with `secrets.token_urlsafe(16)` and printed once. The command MUST refuse to run if any user already exists, exiting `1` with a clear message. There is no HTTP route that creates the first user.

## Notes

- Console script: `disp-admin = "disp.core.cli_admin:app"` (already declared in `pyproject.toml` at M0).
- `MYSTUFF_SEED_PASSWORD` is read directly from `os.environ`, not declared as a `Settings` field — it's a one-shot bootstrap secret, not part of the app's runtime configuration surface, and `Settings`'s `extra="forbid"` only rejects unrecognized fields passed to the constructor, not stray environment variables that don't match declared fields, so this doesn't conflict with `Settings` loading elsewhere in the process.
- Needs a DB session — this is a synchronous-feeling CLI command around async SQLAlchemy, so it should build its own short-lived engine/session (via `disp.core.db.create_engine`/`create_session_maker`, then `session_scope`), run one query to check `SELECT EXISTS (SELECT 1 FROM core.users)`, and either refuse (exit 1) or create the user (reusing `disp.core.auth.passwords.hash_password`).
- Uses `typer` (already pinned) for the CLI shell, consistent with the rest of `disp/cli/` at M14.

## Implementation notes

- Used a plain `SELECT count(*) FROM core.users` (`select(func.count()).select_from(User)`) rather than `SELECT EXISTS(...)`, in the same session/transaction as the subsequent insert, so the refusal check and the create are atomic within one request to the DB.
- **Real bug found and fixed:** a bare `typer.Typer()` with exactly one `@app.command("seed-admin")` and no `@app.callback()` collapses into single-command mode — Click/Typer then treats `disp-admin seed-admin --email ...` as `seed-admin` being an unexpected extra positional argument, since the subcommand name itself gets swallowed by the collapse. Confirmed interactively (`uv run disp-admin seed-admin --email ... --display-name ...` failed with "Got unexpected extra argument(s) (seed-admin)"). Fixed by adding an empty `@app.callback()`, which forces Typer to keep the multi-command subcommand structure even with a single command — re-verified that both `disp-admin --help` (lists `seed-admin` as a subcommand) and `disp-admin seed-admin --email ... --display-name ...` now work exactly as shown in §10.11 and §23.2's one-shot compose command.
- `MYSTUFF_SEED_PASSWORD` read via `os.environ.get(...)` directly (not a `Settings` field, per the note above); when unset, `secrets.token_urlsafe(16)` is generated and printed once via `typer.secho(..., fg=typer.colors.YELLOW)`.
- Verified all three code paths with a fake session/engine (no live Postgres yet — that's M12): (1) refuses with exit code 1 when a user already exists, without touching the insert path; (2) creates the user with `is_admin=True` and a generated password when `MYSTUFF_SEED_PASSWORD` is unset; (3) uses the exact `MYSTUFF_SEED_PASSWORD` value (verified via `verify_password`) when set.
- `ruff`/`ruff format`/`mypy` all clean; full test suite (23 tests, unaffected by this file) still passes.
