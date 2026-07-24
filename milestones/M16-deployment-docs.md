# M16 — Deployment & docs

**Status:** Complete

**Scope:** `Dockerfile`, `docker-compose.yml`, `docker-compose.test.yml`, `scripts/backup.sh`, the full `./dev` script (stub already written at M0), `README.md` (placeholder already written at M0), `docs/{auth,adding-a-module,operations}.md`.

Covers TECHNICAL-SPEC.md §21 (Security requirements — verification checklist), §23 (Deployment), §24 (Developer tooling), §24.1 (Required documentation), §25 (Acceptance criteria), §26 (Out of scope), and Appendix A/B (reference material for docs).

---

## §21. Security requirements (verify against the finished build)

| # | Requirement |
|---|---|
| S1 | Passwords hashed with Argon2id via `pwdlib`. Plaintext never persisted or logged. |
| S2 | Refresh tokens and PATs stored as SHA-256 hashes; plaintext returned exactly once. |
| S3 | Refresh-token reuse revokes the entire token family and logs a `WARNING`. |
| S4 | The refresh cookie is `HttpOnly`, `Secure` (production), `SameSite=Lax`, path-scoped to `/api/auth`. |
| S5 | Cookie-authenticated endpoints require `X-Requested-With: disp`. |
| S6 | Login is constant-time with respect to account existence (dummy verify on the miss path) and returns an identical error for both failure modes. |
| S7 | PATs cannot mint PATs or change passwords. |
| S8 | Authorization is deny-by-default: absence of an ACL row denies. No implicit ownership. |
| S9 | Unreadable resources return `404`, not `403`. |
| S10 | All SQL goes through SQLAlchemy constructs. Raw SQL, if used, is parameterised. String interpolation into SQL is forbidden. |
| S11 | Settings secrets are Fernet-encrypted at rest with a key held only in the environment. |
| S12 | The catch-all exception handler never leaks exception text, SQL, or stack traces to the client. |
| S13 | Rate limits per §17.6. |
| S14 | `docs_url` and `redoc_url` are disabled when `MYSTUFF_ENV=production`. |
| S15 | The container runs as a non-root user (`uid 10001`). |
| S16 | Dependencies are pinned via a committed lock file. |

## §23. Deployment

### 23.1 Dockerfile

Multi-stage. Stage 1 installs dependencies with `uv` into a virtualenv. Stage 2 is `python:3.12-slim`, copies the venv and `src/`, creates user `app` (uid 10001), sets `PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1`, and drops privileges. No build toolchain in the final image.

Default command: `uvicorn disp.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'`.

### 23.2 `docker-compose.yml`

Four services. No identity provider, no auth proxy, no Redis.

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: disp
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?required}
      POSTGRES_DB: disp
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U disp"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  api:
    build: .
    env_file: .env
    depends_on:
      postgres: {condition: service_healthy}
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/live').status==200 else 1)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    restart: unless-stopped
    labels:
      - traefik.enable=true
      - traefik.http.routers.disp.rule=Host(`${PUBLIC_HOST}`)
      - traefik.http.routers.disp.tls.certresolver=le
      - traefik.http.services.disp.loadbalancer.server.port=8000

  worker:
    build: .
    command: ["python", "-m", "disp.worker"]
    env_file: .env
    depends_on:
      postgres: {condition: service_healthy}
    restart: unless-stopped

  traefik:
    image: traefik:v3.2
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.web.address=:80
      - --entrypoints.websecure.address=:443
      - --entrypoints.web.http.redirections.entrypoint.to=websecure
      - --certificatesresolvers.le.acme.email=${ACME_EMAIL}
      - --certificatesresolvers.le.acme.storage=/letsencrypt/acme.json
      - --certificatesresolvers.le.acme.httpchallenge.entrypoint=web
    ports: ["80:80", "443:443"]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - letsencrypt:/letsencrypt
    restart: unless-stopped

volumes:
  pgdata:
  letsencrypt:
```

Migrations and schema application are explicit one-shot commands, never part of container startup:

```
docker compose run --rm api ./dev migrate
docker compose run --rm api procrastinate --app=disp.core.scheduler.app schema --apply
docker compose run --rm api disp-admin seed-admin --email you@example.com --display-name "You"
```

### 23.3 Backups

`docs/operations.md` MUST document, and the repo MUST include as `scripts/backup.sh`:

- Nightly `pg_dump -Fc` to a timestamped file.
- Retention: 7 daily, 4 weekly.
- Off-host copy (S3 or rsync), with the destination configurable.
- **A restore procedure that has been executed at least once**, documented step by step.
- An explicit warning that `MYSTUFF_SETTINGS_KEY` must be backed up separately and that losing it makes every stored notification credential unrecoverable, while losing `MYSTUFF_JWT_SECRET` only invalidates outstanding access tokens.

> `scripts/backup.sh` isn't itemized in §4's repository tree, but is explicitly mandated here — added under a new `scripts/` directory as a reasonable gap-fill (same category as `docker-compose.test.yml`, resolved with the user at planning time as: minimal Postgres-only override, not used by pytest which uses testcontainers).

## §24. Developer tooling

`./dev` is an executable bash script with `set -euo pipefail` implementing:

| Command | Action |
|---|---|
| `./dev up` | `docker compose up -d` |
| `./dev down` | `docker compose down` |
| `./dev migrate [branch]` | Upgrade all branches, or one |
| `./dev makemigration <branch> "<msg>"` | Autogenerate a revision |
| `./dev test [args…]` | `pytest` with coverage gates |
| `./dev lint` | `ruff check` + `ruff format --check` + `mypy src` |
| `./dev fmt` | `ruff format` + `ruff check --fix` |
| `./dev shell` | `psql` into the dev database |
| `./dev seed` | Seed an admin and three sample notes for local work |
| `./dev openapi` | Write `openapi.json` to the repo root |

`ruff` configuration: line length 100; rule sets `E, F, I, N, UP, B, S, A, C4, DTZ, RUF`; `S101` ignored under `tests/`.

`mypy`: `strict = true` for `src/disp/core/`, default strictness elsewhere; `disallow_untyped_defs = true` everywhere. The build fails on any error.

(The `dev` script and `ruff`/`mypy` config in `pyproject.toml` were already written at M0; this milestone is where `./dev seed` gets real content once `disp-admin`/notes exist, and where the whole script gets exercised against the live compose stack.)

### 24.1 Required documentation

- `README.md` — what this is, quickstart (clone → `.env` → `./dev up` → migrate → seed admin → `disp login`), the architecture in one diagram, and where to read more.
- `docs/adding-a-module.md` — a four-step recipe with a complete, copy-pasteable minimal module, plus the rules a module must obey (own schema, own migration branch, no cross-module imports, auth via the three public names only).
- `docs/auth.md` — the credential types, their lifetimes, the rotation and reuse-detection behaviour, the accepted 15-minute revocation window for access tokens, and the four-step procedure for adopting an external OIDC provider later.
- `docs/operations.md` — backups, restore drill, key rotation, log locations, health endpoints.

## §25. Acceptance criteria (final checklist before declaring done)

See TECHNICAL-SPEC.md §25 in full — covers build/run, plug-in mechanism, auth, authorization, platform services, API quality, CLI, and quality gates (`./dev lint` zero findings, `./dev test` ≥85%/≥95%, no stray `TODO`/`FIXME`/`NotImplementedError` except the documented `oidc.py` stub, all four docs present and accurate).

## §26. Out of scope (do not build)

Any web UI; the plants, habits, or shopping-list modules; email delivery; password reset by email; TOTP or WebAuthn; OIDC or SAML; audit-log UI; multi-tenancy; Kubernetes manifests; CI pipeline definitions; a Textual TUI (the Typer CLI only).

## Appendix A — Error code registry (reference for docs)

See TECHNICAL-SPEC.md Appendix A for the full table. Two codes were added beyond the spec's literal enumeration during implementation, following the exact same naming convention as existing codes (documented in `docs/` as an addendum, not a spec violation):
- `auth.token_not_found` (404) — `DELETE /api/auth/tokens/{id}` when the token doesn't exist or isn't the caller's (§10.7's endpoint table requires this 404 behavior; Appendix A simply omitted a code for it).

## Appendix B — Worked examples (reference for docs)

See TECHNICAL-SPEC.md Appendix B for login, PAT-authenticated note creation, tile response, error response, and the complete `hello` fixture module examples — useful source material for `README.md` and `docs/adding-a-module.md`.

## Implementation notes

**Scope note — "deployment" here means artifacts and documentation, not an actual deployment.**
Per explicit user instruction, this milestone produced the Dockerfile, compose files, backup
script, and docs, and verified them locally (a Docker build, and one real backup+restore drill
against the local dev Postgres) — it did **not** stand up the production `docker-compose.yml`
stack (Traefik/ACME/public hosting), which was never available to stand up in this environment
anyway.

**Files added:** `Dockerfile`, `docker-compose.yml`, `docker-compose.test.yml`, `scripts/backup.sh`,
`docs/{auth,adding-a-module,operations}.md`, plus a rewritten `README.md`. `.dockerignore` was
amended (`*.md` / `!README.md`) since `pyproject.toml` declares `readme = "README.md"`, needed by
`uv sync` inside the build — a bare `*.md` exclusion would have broken the build. `dev`'s `up`,
`down`, and `shell` commands were pointed at `docker-compose.test.yml` explicitly (`-f` flag): the
plain `docker-compose.yml` is the *production* stack (includes Traefik, requires `PUBLIC_HOST`/
`ACME_EMAIL`), which local dev has no use for — local dev runs the API/worker directly via
`uv run`, only needing a bare Postgres container.

### Verification performed

- **Docker build**: `docker build -t disp:verify .` — builds clean, multi-stage, final image has
  no build toolchain, runs as uid 10001 (S15). Building alone wasn't enough to catch the two bugs
  below — both only surfaced by actually running the image.
- **Two real Docker bugs found and fixed by running the built image**, not just building it:
  1. `uv sync`'s default install mode is *editable* — `import disp` inside the container raised
     `ModuleNotFoundError`, because the venv's `disp` package was a `.pth` link back to the
     builder stage's `/build/src`, a path that doesn't exist in the runtime stage. Fixed with
     `uv sync --frozen --no-dev --no-editable` in the builder.
  2. Even after that fix, every installed console script (`alembic`, `disp-admin`, `procrastinate`,
     `disp`) failed with `exec: no such file or directory` — `uv sync` bakes an **absolute**
     shebang line (`#!/build/.venv/bin/python`) into each script at creation time, and the builder
     stage's `WORKDIR /build` didn't match the runtime stage's `WORKDIR /app`. Fixed by building
     at `/app` in the builder stage too, so the shebang path is valid after copying the venv
     across. Verified after the fix: `alembic --version`, `disp-admin --help`,
     `python -c "from disp.core.app import create_app; create_app()"` (with real dummy env vars,
     discovered `notes` and wired 6 routes), and a genuine `uvicorn disp.main:app` boot against
     the local dev Postgres (via `--network host`), which started, served, and shut down cleanly
     on a 5-second timeout — the image runs, not just builds.
  3. Consequence of not shipping `uv`/`./dev` in the runtime image (a deliberate choice — see
     "no build toolchain" S-requirement): the spec's literal `docker compose run --rm api
     ./dev migrate` example doesn't work as written, since `./dev migrate` shells out to `uv run
     alembic`. `docs/operations.md` documents the verified equivalent using the installed
     `alembic`/`procrastinate`/`disp-admin` console scripts directly instead.
- **Backup + restore drill (§23.3's "executed at least once" requirement)**: ran `pg_dump` inside
  the live `disp-postgres-dev` container (16.14), restored the dump into a scratch database
  (`disp_restore_test`), verified all 8 `core.*` tables reappeared and `core.users` row counts
  matched exactly (1 == 1) between source and restore, then dropped the scratch database. The
  exact commands and their real output are reproduced verbatim in `docs/operations.md`'s restore
  section — not invented from the spec's description.
- **Bug found during the drill**: the host's `pg_dump` (Homebrew, v14.21) refused to dump the v16.14
  server (`pg_dump: error: server version: 16.14; pg_dump version: 14.21 ... aborting because of
  server version mismatch`). This is a real, easy-to-hit operational trap — documented as an
  explicit prerequisite in `docs/operations.md` (the backup host needs a `pg_dump`/`pg_restore`
  client whose major version is at least the server's), discovered by actually running the
  verification rather than just writing the script from the spec's description.
- **§21 security checklist**: spot-checked the items not already exercised by an automated test —
  S1 (`PasswordHash.recommended()` = Argon2id), S2 (SHA-256 hashing in `tokens.py`/`invites.py`),
  S14 (`docs_url`/`redoc_url` gated on `settings.env != "production"`), S15 (Dockerfile creates and
  drops to uid 10001), S16 (`uv.lock` present). S3–S13 were not re-verified by hand here since
  they're each covered by a specific, still-passing M15 test case (refresh reuse, cookie flags,
  CSRF header, constant-time login, PAT restrictions, ACL deny-by-default, 404-vs-403, parameterized
  SQL throughout via SQLAlchemy constructs, settings encryption, exception-handler leak safety,
  rate limits) — re-deriving that evidence by hand would just be restating the M15 test suite.
- **Stray-marker check**: `grep -rn "TODO\|FIXME" src/` — none. `grep -rn "NotImplementedError" src/`
  — exactly one hit, `oidc.py`'s documented stub, matching §25's checklist exactly.
- `TODO.md` updated to reflect all sixteen milestones complete (it had been stale since M9).

### Documentation notes

- `docs/operations.md`'s key-rotation table for `MYSTUFF_SETTINGS_KEY` was drafted first assuming
  an HTTP endpoint could reveal secret values in plaintext for pre-rotation recovery — checked
  against `settings_store.py`'s actual router and found no such endpoint exists (`GET
  /api/settings/{domain}` always masks secrets, by design, §14.3). Corrected to describe the real
  mechanism: a one-off script instantiating `SettingsStore` directly with the old key and calling
  `get_all(..., reveal_secrets=True)`, which is a genuine Python-level capability, just not one
  exposed over HTTP.
- `docs/adding-a-module.md`'s module-boundary section documents the *actual* resolved
  `disp.core.auth` public surface (ten names) rather than the spec's original literal five-name
  enumeration, cross-referencing `milestones/M06-auth.md` for the resolution rationale — keeping
  the docs consistent with what the boundary test in `tests/core/test_boundaries.py` actually
  enforces, not with the spec's literal (superseded) code block.
