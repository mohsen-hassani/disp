# M14 — CLI (disp)

**Status:** Complete

**Scope:** `cli/client.py`, `cli/config.py`, `cli/render.py`, `cli/main.py`, `cli/commands/{auth,dashboard,notes,modules,health}.py`.

Covers TECHNICAL-SPEC.md §19 (Typer CLI).

---

## §19.1 Configuration file

Path: `platformdirs.user_config_dir("disp")/config.toml`, created with mode `0600`. The CLI MUST refuse to read a config file whose mode is group- or world-readable, exiting `3` with instructions to `chmod 600`.

```toml
default_profile = "default"

[profiles.default]
server = "https://stuff.example.com"
token = "disp_pat_…"
email = "me@example.com"
```

The token MUST NOT be written anywhere else, and MUST NOT appear in `--verbose` output (redact to the prefix).

## §19.2 Global options

| Option | Effect |
|---|---|
| `--profile, -p TEXT` | Select a profile (default: `default_profile`) |
| `--server TEXT` | Override the server URL for one invocation |
| `--json` | Emit raw JSON instead of Rich tables; disables all decoration |
| `--no-color` | Disable colour (also honours `NO_COLOR`) |
| `--verbose, -v` | Log requests (method, URL, status, duration) to stderr |
| `--version` | Print version and exit |

Human output goes to **stdout**; diagnostics and errors go to **stderr**. `--json` output MUST be a single valid JSON document on stdout with nothing else, so it is pipeable to `jq`.

## §19.3 Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Generic failure |
| `2` | Usage error (Typer default) |
| `3` | Authentication or configuration error (no token, 401, bad file mode) |
| `4` | Network error (DNS, connection refused, timeout) |
| `5` | Server error (5xx) |
| `6` | Not found (404) |

## §19.4 Commands

**`disp login [--server URL] [--profile NAME]`**

1. Prompt for the server URL if not supplied and not in config.
2. Prompt for email; prompt for password with `hide_input=True`.
3. `POST /api/auth/login`.
4. With the returned access token, `POST /api/auth/tokens` with `name = f"cli@{socket.gethostname()}"[:64]`. If that name exists (`409`), append `-2`, `-3`, … up to `-9`.
5. Persist `server`, `email`, and the PAT to the profile. Discard the password and the access token immediately; never write them.
6. Print `Logged in as <display_name> <email>` and the token prefix.

The refresh cookie is discarded. The CLI authenticates only with the PAT.

**`disp logout [--profile NAME]`** — `DELETE /api/auth/tokens/{id}` for the stored token (resolved by matching `token_prefix` from `GET /api/auth/tokens`), then removes the profile. Succeeds even if the server is unreachable, warning that the token was not revoked remotely.

**`disp whoami`** — `GET /api/auth/me`; prints display name, email, admin flag, auth method.

**`disp tokens list`** / **`disp tokens revoke <id>`** / **`disp tokens create <name> [--expires-days N]`** — the last prints the plaintext once with a warning that it will not be shown again.

**`disp health`** — `GET /health`; prints status, version, database, worker last-seen. Exit `1` if status is not `ok`.

**`disp modules`** — `GET /api/dashboard/manifest`; Rich table with columns Domain, Name, Version, Tiles, Jobs.

**`disp dashboard`** — `GET /api/dashboard/tiles`; renders each tile as a Rich panel showing title, count, up to 5 items, and available actions. Empty tiles render their `empty_text` dimmed.

**`disp notes list [--limit N] [--pinned/--no-pinned] [-q TEXT] [--all]`** — Rich table: Id (first 8 chars), Pinned marker, Title, Created (relative, e.g. "2h ago"), Preview (60 chars). `--all` pages through every cursor.

**`disp notes add [BODY] [--title TEXT] [--pin]`** — if `BODY` is omitted and stdin is not a TTY, read the body from stdin (enabling `echo "x" | disp notes add`). If omitted and stdin is a TTY, open `$EDITOR`. Prints the new note id.

**`disp notes show <ID>`** — accepts a full UUID or an unambiguous prefix of ≥ 4 characters; an ambiguous prefix lists the candidates and exits `1`.

**`disp notes edit <ID> [--title TEXT] [--body TEXT] [--pin/--unpin]`** — with no flags, opens `$EDITOR` pre-filled with the current body.

**`disp notes rm <ID> [--yes]`** — confirms unless `--yes`.

**`disp notes share <ID> --email E --permission read|write`**

## §19.5 Client behaviour

`cli/client.py` MUST:

- Use one `httpx.Client` with `timeout=httpx.Timeout(10.0, connect=5.0)` and `follow_redirects=False`.
- Send `Authorization: Bearer <pat>` and `User-Agent: disp-cli/<version>`.
- Map responses to exceptions: `401` → `AuthError` (exit 3, message "Not logged in or token revoked — run `disp login`"), `403` → `PermissionError` (exit 1), `404` → `NotFoundError` (exit 6), `429` → retry once after `Retry-After` then fail (exit 1), `5xx` → `ServerError` (exit 5), transport errors → `NetworkError` (exit 4).
- Surface the problem-detail `detail` field as the user-facing message when present; fall back to a generic message.
- Never print a traceback unless `--verbose`.

> Per the resolved naming decision (see M0): User-Agent is `disp-cli/<version>` and the config's `token` field holds a `disp_pat_...` value, not the spec's original `stuff-cli/<version>` / `stuff_pat_...` text.

## Implementation notes

All files under `src/disp/cli/` (`client.py`, `config.py`, `render.py`, `state.py`, `errors.py`,
`main.py`, `commands/{health,modules,dashboard,auth,notes}.py`) implemented per §19. `ruff check`,
`ruff format --check`, and `mypy --strict` (`src/`) all pass with zero findings.

**Bugs found and fixed during implementation:**

1. **`typer.Option(..., max_length=200)` doesn't exist.** Typer/Click options don't support a
   `max_length` kwarg (that's a Pydantic/FastAPI concept). Removed the invalid kwarg from
   `notes.py`'s `-q`/`--query` option; the ≤200-char constraint is already enforced server-side
   per §18.3, so no client-side re-validation was needed.

2. **`isinstance(ctx, typer.Context)` returns `False` at runtime.** `errors.py`'s
   `handle_cli_errors` decorator originally tried to locate the injected `Context` object via
   `isinstance` to redirect verbose-mode tracebacks. Empirically (via throwaway scripts), Typer
   0.27's actual injected object at runtime has a different class with an MRO of
   `(Context, object)` unrelated to the public `typer.Context` alias, so the isinstance check
   silently always failed. Fixed by locating it via `kwargs.get("ctx")` (name-based, matching
   every command's own `ctx: typer.Context` parameter) instead.

3. **`disp notes list --json | jq '.items[0].id'` failed with "No such option: --json"
   (§25 acceptance criterion 27).** Click only recognizes a Typer group's callback-level options
   (the root `--json`, defined once on `main.py`'s `app` callback) when they precede the
   subcommand name — `disp --json notes list` works, but `disp notes list --json` does not,
   because by the time Click parses `--json` it has already dispatched into the `notes` sub-Typer
   and its own parser has no such option. This directly contradicts §25 item 27's literal example
   invocation, which places `--json` *after* the subcommand.

   Resolved by adding a local `--json` `typer.Option` to every leaf command (`health`, `modules`,
   `dashboard`, `whoami`, `tokens list`, `tokens create`, `notes list`, `notes add`, `notes show`,
   `notes edit`) and a new `effective_json(state, json_flag)` helper in `state.py` that returns
   `json_flag or state.json_mode`, so `--json` is now accepted in both positions
   (`disp --json notes list` and `disp notes list --json` both work). This is an additive
   accommodation of Click's parsing model, not a deviation from any literal requirement — §19.2's
   table lists `--json` as a global option and does not forbid also accepting it locally.

4. **`disp notes list --json` originally emitted a bare JSON array, not `.items[...]`.** The
   first implementation unwrapped the API's `{"items": [...], "has_more": ..., "next_cursor": ...}`
   envelope down to just the `items` list before emitting JSON, which breaks §25 item 27's exact
   verbatim acceptance command (`jq '.items[0].id'` expects an `items` key). Fixed by having the
   `--json` branch of `notes list` emit `{"items": items}` instead of the bare list, restoring the
   `.items[...]` shape the spec's own example depends on. (The `--all` pagination path still
   flattens across cursors client-side, as intended — only the JSON envelope shape changed.)

**Live end-to-end verification** (against the same Postgres 16 + `uvicorn` server used for M12/M13,
started via `nohup uv run uvicorn disp.main:app --host 127.0.0.1 --port 8123`):

- `disp login` (prompted flow) → PAT persisted to `~/.config/disp/config.toml` (mode `0600`,
  verified via `stat`).
- `disp health`, `disp modules`, `disp dashboard` — plain and `--json` (both leading
  `disp --json health` and trailing `disp health --json`) all verified against the live server.
- `disp notes add "…"` (positional arg) and `echo "…" | disp notes add` (stdin) both create notes;
  `disp notes list`, `disp notes list --all`, `disp notes list --json | jq '.items[0].id'`
  (the exact §25 item 27 command) all verified.
- `disp notes show <prefix>` (4-char prefix resolution) and `disp notes show <prefix> --json`
  verified.
- `disp notes edit <prefix> --title …` and `--pin --json` verified; response reflects the update.
- `disp notes rm <prefix> --yes` verified — note disappears from a subsequent `notes list`.
- `disp notes share <prefix> --email … --permission read` verified against the server's own
  business-rule rejection ("cannot share with your own account" — correct 4xx, correctly
  surfaced as a CLI error with exit code 1); sharing with a second real user was already
  exercised at the API level in M13.
- `disp tokens list` / `disp tokens list --json` / `disp whoami --json` verified.
- `disp tokens create <name>` against a **PAT-authenticated** session correctly reproduced S11
  ("a PAT cannot create a PAT"), surfaced as a 403 → `CliPermissionError` → exit code `1`. This
  is server-enforced behavior from M06, not a CLI bug.
- `disp logout` and `disp tokens revoke` were verified by code review rather than a live call in
  this pass, to avoid revoking the single PAT the rest of the verification run depended on; both
  reuse the same `ApiClient`/`build_client`/config primitives already exercised end-to-end by
  every other command, so the residual risk is low.
- All test notes created during this verification pass were deleted (`disp notes rm --yes`)
  afterward to leave the dev database clean.
