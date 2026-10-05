# Operations

## First deploy: migrations, schema, and the first admin

Migrations and schema application are explicit one-shot commands, never part of container
startup. The production image (`Dockerfile`) intentionally does **not** ship `uv` or the `./dev`
script — only the installed package and its console-script entry points (`alembic`, `disp-admin`,
`procrastinate`) — so run these directly rather than through `./dev migrate`:

```
docker compose run --rm api alembic --name=core upgrade head
docker compose run --rm api alembic --name=notes upgrade head
docker compose run --rm api alembic --name=plants upgrade head
docker compose run --rm api procrastinate --app=disp.core.scheduler.app schema --apply
docker compose run --rm api disp-admin seed-admin --email you@example.com --display-name "You"
```

(Add one more `alembic --name=<branch> upgrade head` line per module with its own migration
branch, as modules are added — see `docs/adding-a-module.md`.) All three console scripts were
verified against a real Postgres 16 as part of writing this document.

### File storage: Cloudflare R2 (M18 v2)

Uploaded files live in an S3-compatible bucket — Cloudflare R2 in production — never on a volume
(`docs/milestones/server/M18-files.md`). One-time setup:

1. **Create a bucket** in the R2 dashboard (e.g. `disp-media`). Use a *separate* bucket for any
   non-production environment: the hourly sweeper deletes every object under the prefix that has no
   row in *its own* database, so a dev database pointed at the production bucket would treat every
   production file as garbage.
2. **Create an R2 API token** scoped to that bucket only, with *Object Read & Write*. Note the access
   key id, the secret, and the S3 endpoint `https://<account-id>.r2.cloudflarestorage.com`.
3. **Set, in `.env`, for both `api` and `worker`:**
   ```
   DISP_FILES_S3_BUCKET=disp-media
   DISP_FILES_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
   DISP_FILES_S3_ACCESS_KEY_ID=...
   DISP_FILES_S3_SECRET_ACCESS_KEY=...
   ```
   The API refuses to boot if the bucket or either credential is empty.
4. **(Belt and braces) add a lifecycle rule** "abort incomplete multipart uploads after 1 day". The
   platform never starts a multipart upload (every file is a single `PutObject`), so this only guards
   against a future change billing you for half-finished uploads.
5. No CORS rule is needed: `<img>`/`<video>` loads of presigned links don't require one. The web
   client's CSP already allows `https://*.r2.cloudflarestorage.com` (`clients/web/security-headers.conf`).
   **Moving to a provider other than R2 means editing that CSP line.**

### File maintenance commands

Neither command needs the app running; each builds its own database connection and talks to the
bucket directly.

```
docker compose run --rm api disp-admin files verify   # read-only bucket <-> table diff
docker compose run --rm api disp-admin files sweep    # run core.sweep_files now
```

- **`verify`** lists the bucket once (under `DISP_FILES_S3_PREFIX`) and compares it with
  `core.files`. It reports:
  - rows whose object is missing;
  - objects no row references;
  - rows still awaiting purge;
  - rows in another bucket or backend, which it does not check.

  It **deletes nothing**. Run it first after any database restore (step 7 of "Restore procedure" below).
- **`sweep`** runs the same two passes as the hourly `core.sweep_files` job, immediately:
  - it purges every row marked deleted (object, then row);
  - it deletes unreferenced objects older than `DISP_FILES_ORPHAN_GRACE_SECONDS`.

  Use it to reclaim storage right away instead of waiting for the next `:17`. Like the job, it
  never deletes a row just because its object is missing. **Don't run it right after a restore
  before `verify`:** objects the restored database no longer references count as orphans, and
  `sweep` deletes them.

### Upgrading from M18 v1 (local `media` volume) to v2

v2 started fresh by decision: existing uploaded files are **not** migrated.

1. **Remove the v1 keys from `.env`** — `DISP_FILES_ROOT`, `DISP_FILES_URL_TTL_SECONDS`,
   `DISP_FILES_SWEEP_GRACE_SECONDS`, `DISP_FILES_S3_NATIVE_PRESIGN`. `Settings` is
   `extra="forbid"` and reads `.env` directly, so a leftover key **refuses to boot** with a
   pydantic "extra inputs are not permitted" error.
2. Add the R2 settings above.
3. Migrate:
   ```
   docker compose run --rm api alembic --name=core upgrade head       # 0005: drops core.assets, creates core.files
   docker compose run --rm api alembic --name=plants upgrade head     # 0003: image_asset_id -> image_file_id, nulled
   docker compose run --rm api alembic --name=learning upgrade head   # asset_id -> file_id, nulled
   ```
4. Once the new stack is up, delete the orphaned volume: `docker volume rm disp_media`.

## SSH deploy

> **Currently disabled.** While `disp` moves to Kubernetes (`k8s/roadmap.md`), the workflow's
> `deploy` job is switched off with `if: false`: a push to `prod` only builds and pushes both
> images (`disp`, `disp-web`) to the registry, and nothing SSHes into the host. The rest of this
> section describes the compose deploy path as it works when that job is enabled, and stays
> accurate for re-enabling it. Roadmap T12 replaces it with GitOps, and T14 decides whether to
> keep it as a fallback or remove it.

Every push to `prod` (`.github/workflows/deploy.yml`) builds the image, pushes it to
`registry.mohsen-hassani.com` under two tags
(`registry.mohsen-hassani.com/mohsen_hassani/disp:<12-char-sha>` and `:latest`), then SSHes into
the production host
and runs a single command: `./scripts/deploy.sh <sha-tag>`. The script starts with `git pull
--ff-only` so the host's compose files (and the script itself) stay in sync with what was pushed,
then never runs migrations — those stay the explicit, manual step above, on purpose, so a deploy
can never silently apply one.

Traefik itself is **not** part of this repo — it's shared infrastructure for every app on the
droplet, defined in a separate `infra` project (`../infra` alongside this repo; see that project's
`README.md`). This repo's `docker-compose.yml` only joins Traefik's `edge` network and carries the
routing labels on `api` — bring the `infra` stack up first, or `docker compose up` here will fail
with `network edge declared as external, but could not be found`.

**One-time host setup**, assuming `/opt/disp` already holds a `git clone` of this repo checked out
on `prod` (so `git pull --ff-only` in the script has a remote to pull from) with a real `.env` (with
`IMAGE_REGISTRY`/`IMAGE_TAG` set per
`.env.example`), and the `infra` project (see above) is already up:

1. Create a dedicated deploy user on the host (or reuse an existing one) that can run `docker
   compose` in `/opt/disp` without a password prompt, and generate a dedicated SSH keypair for it
   (`ssh-keygen -t ed25519 -f deploy_key -N ""` — don't reuse a personal key).
2. Append the public half (`deploy_key.pub`) to that user's `~/.ssh/authorized_keys` on the host.
3. Run `ssh-keyscan -t ed25519 <host>` from any machine to capture the host's public key.
4. In the GitHub repo's Settings → Secrets, set `SSH_HOST` (the droplet's address), `SSH_USER`
   (the deploy user from step 1), `SSH_PRIVATE_KEY` (the private half from step 1, full
   `-----BEGIN OPENSSH PRIVATE KEY-----` block), `SSH_KNOWN_HOSTS` (the output of step 3) —
   the last one pins the host key so the workflow's SSH step can't be MITM'd by silently trusting
   whatever key it's offered — and `REGISTRY_USERNAME`/`REGISTRY_PASSWORD` (credentials for
   `registry.mohsen-hassani.com`, used by `docker/login-action` in the build job).
5. On the host, also `docker login registry.mohsen-hassani.com` as whatever user runs
   `docker compose pull` in `scripts/deploy.sh` — pulling a private image needs the host
   authenticated too, not just the GitHub Actions build job that pushes it.
6. In the `infra` project, confirm `traefik-dynamic.yml`'s `Host()` rule matches the real
   `PUBLIC_HOST` from this repo's `.env` (Traefik's file provider does not expand `${PUBLIC_HOST}`
   the way Compose does — this has to be edited by hand and kept in sync manually), then restart
   Traefik there to pick it up: `docker compose up -d traefik` (run from `infra`, not from here).

**On every push to `prod`**: `scripts/deploy.sh` runs on the host (invoked over SSH by the
workflow), writes the new tag into `.env`, `docker compose pull && up -d` for `api`/`worker`/`web`
(M12) only — never `postgres`/`pgweb` — and polls `GET /health` (readiness, not the liveness-only
`/health/live`) up to 6 times over 30 seconds. `api` publishes no host port (Traefik/`edge`-network
only), so this runs via `docker compose exec api python -c ...` inside the container's own network
namespace rather than curling it from the host. On failure it restores the previous `IMAGE_TAG`,
recreates the containers again, and exits non-zero — which makes the SSH command itself exit
non-zero, which is what makes the triggering Actions run go red rather than reporting a false
success.

## Health endpoints

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /health` | none | Overall status: database connectivity, discovered modules, worker last-seen timestamp. Returns `503` when the database is unreachable. |
| `GET /health/live` | none | Liveness probe — no database access. Always `200` if the process is up. Use this for container/orchestrator liveness checks; use `/health` for a real readiness signal. |

## Log locations

The API and worker both log structured JSON (or console-formatted text when `DISP_LOG_FORMAT=console`) to stdout/stderr — there is no log file on disk. Under `docker compose`, retrieve logs with:

```
docker compose logs -f api
docker compose logs -f worker
```

Every HTTP request log line includes `request_id`, which also appears in every `application/problem+json` error body's `request_id` field — use it to correlate a user-reported error with the corresponding log line. Refresh-token reuse (a potential credential-theft signal) logs at `WARNING` with `user_id` and `family_id`; treat repeated occurrences as worth investigating.

### LLM cost monitoring

`GET /api/llm/usage` (admin-only) reports token and call totals grouped by call name and day. For anything the endpoint doesn't aggregate, query `core.llm_call` directly — it holds every call's outcome, model, and token counts (never a prompt or completion; see the backup note below).

## Backups

`scripts/backup.sh` performs a nightly logical backup:

- `pg_dump -Fc` (custom/compressed format) to `$BACKUP_DIR/disp-<UTC timestamp>.dump` (default `BACKUP_DIR=/var/backups/disp`).
- Retention: the 7 most recent daily dumps, plus one dump per week for 4 further weeks. Everything older is pruned.
- If `BACKUP_REMOTE` is set (an `s3://...` URI or an `rsync`-style `user@host:/path`), the fresh dump is copied off-host immediately after the local dump completes.

### Uploaded files are not in the database dump

`scripts/backup.sh` covers Postgres only. Uploaded bytes live in the R2 bucket, and **R2 does not
version objects**: a file deleted through the platform is purged from the bucket right after the
deleting transaction commits (M18 §8.2), with no undo. If you need file backups, mirror the bucket
off-site (e.g. a nightly `rclone sync r2:disp-media /var/backups/disp/media`). The platform does not
do this for you.

Restoring an older database dump can produce `core.files` rows whose objects have since been purged,
and the bucket can hold objects newer than the dump. Run `disp-admin files verify` after any restore
(step 7 below).

Run the database backup nightly via cron, e.g.:

```cron
0 3 * * * cd /opt/disp && DISP_DATABASE_URL_SYNC=... BACKUP_REMOTE=s3://my-bucket/disp-backups/ ./scripts/backup.sh >> /var/log/disp-backup.log 2>&1
```

**Prerequisite:** the host running `backup.sh` needs a `pg_dump`/`pg_restore` client whose major version is **at least** the Postgres server's (16). A mismatched client refuses to run (`pg_dump: error: server version: 16.14; pg_dump version: 14.21 ... aborting because of server version mismatch`) — this was hit and fixed during verification of this exact document, by running `pg_dump` inside the `postgres:16-alpine` container itself rather than relying on the host's client. In production, run the backup from a container built on the same Postgres image (or install a matching `postgresql-client-16` package on the backup host).

### ⚠️ `DISP_SETTINGS_KEY` needs its own backup

`pg_dump` backs up the **database**, not the environment. `core.settings.value_encrypted` is Fernet-encrypted with `DISP_SETTINGS_KEY`, which lives only in the environment (S11) — it is never stored in the database. **If `DISP_SETTINGS_KEY` is lost, every encrypted setting (currently: notification-channel Apprise URLs) becomes permanently unrecoverable, even with a perfect database restore.** Back this key up separately, in a secrets manager or an offline copy — not alongside the `pg_dump` output.

By contrast, losing `DISP_JWT_SECRET` is low-severity: it only invalidates every outstanding access token (users re-authenticate via their still-valid refresh cookie or PAT) and does not affect any stored data.

### `DISP_LLM_API_KEY` and `DISP_EMBEDDING_API_KEY` also live only in the environment

Like `DISP_SETTINGS_KEY`, neither credential is ever written to the database (`docs/milestones/server/M19-llm.md` §3 — putting it in `core.settings` would be circular, since the settings store needs `DISP_SETTINGS_KEY` to decrypt its own secret fields before it could produce this one). Unlike `DISP_SETTINGS_KEY`, **losing either key is not a data-loss event**: both are re-issuable from the provider (the Anthropic console, or Voyage AI's), so a lost key is an inconvenience, not something to treat as a restore scenario. `core.llm_call` never stores a prompt or completion either (L2), so there is nothing to recover from a database backup even in principle.

### `DISP_TRANSLATION_API_KEY` too — with one rotation trap the others don't have

Same story as the two keys above (`docs/milestones/server/M22-translation.md` §3, §12): environment-only, never persisted, re-issuable from the provider, and `core.translation_call` stores no source or translated text (T6), so a lost key is an inconvenience rather than a restore scenario.

**The trap is the API host.** A DeepL free-tier key ends in `:fx` and must reach `api-free.deepl.com`; a paid key must reach `api.deepl.com`. The backend derives the right host from the key's suffix **only when `DISP_TRANSLATION_BASE_URL` is empty**. So if that variable was ever set explicitly — for a proxy, or to pin a host — then upgrading a free key to a paid one silently 403s every call with a message that reads like a bad credential. Clear or update `DISP_TRANSLATION_BASE_URL` in the same change as the key, or leave it unset and let the derivation do its job.

### Watching the translation character budget

Providers meter **source characters**, and a free tier is a hard monthly ceiling (DeepL: 500 000, returning `456`, surfaced as `TranslationQuotaExceeded`) rather than an overage charge — so the useful question is "how many characters this month", not "how many calls".

```
docker compose run --rm api disp-admin translation usage --days 30
docker compose run --rm api disp-admin translation usage --days 30 --backend deepl
```

One line per (day, backend, operation, outcome) group plus a total. There is deliberately no HTTP endpoint for this (M22 §10); `core.translation_call` is available directly for anything the command does not aggregate. Note that a free account's ceiling resets on the billing date, not the 1st.

### The `pgvector/pgvector:pg16` image swap (M19) is a rebuild, not a data migration

All three compose files and the test container now run `pgvector/pgvector:pg16` instead of stock `postgres:16-alpine`/`postgres:16`. This is the same Postgres 16 with the `vector` extension available, not installed by default — existing volumes mount unchanged, and there is no dump/restore step. An operator who reads "new database image" and schedules a maintenance window for a migration is doing unnecessary work; a plain image pull and container recreate is sufficient.

### Restore procedure (verified)

This procedure was executed against a real dump of the dev database as part of writing this document — not just written from the spec. Commands and output below are the actual verified run (against `postgres:16-alpine` in a local container; identical against production, modulo container/host names).

1. **Take or locate a dump:**

   ```
   $ docker exec disp-postgres-dev pg_dump -Fc -U disp_user -d disp_db -f /tmp/disp-test.dump
   ```

2. **Create an empty target database** (never restore over the live one directly — see step 4):

   ```
   $ docker exec disp-postgres-dev psql -U disp_user -d postgres -c "CREATE DATABASE disp_restore_test OWNER disp_user;"
   CREATE DATABASE
   ```

3. **Restore the dump:**

   ```
   $ docker exec disp-postgres-dev pg_restore -U disp_user -d disp_restore_test /tmp/disp-test.dump
   ```

   (No output on success — `pg_restore` is silent unless something fails.)

4. **Verify the restore before cutting over.** At minimum, confirm the expected tables exist and row counts are sane:

   ```
   $ docker exec disp-postgres-dev psql -U disp_user -d disp_restore_test -c "\dt core.*"
                  List of relations
    Schema |         Name         | Type  | Owner
   --------+----------------------+-------+-------
    core   | acl                  | table | disp_user
    core   | alembic_version_core | table | disp_user
    core   | api_tokens           | table | disp_user
    core   | invites              | table | disp_user
    core   | notification_log     | table | disp_user
    core   | sessions             | table | disp_user
    core   | settings             | table | disp_user
    core   | users                | table | disp_user
   (8 rows)

   $ docker exec disp-postgres-dev psql -U disp_user -d disp_restore_test -tAc "SELECT count(*) FROM core.users;"
   1
   ```

   Compare the row count against the source database (`psql -d disp_db -tAc "SELECT count(*) FROM core.users;"`) — it matched exactly in this verification run.

5. **Cut over.** Once verified, either:
   - Point `DISP_DATABASE_URL` at the restored database and restart the API/worker, or
   - Rename the live (broken) database aside and rename the restored one into its place, inside a maintenance window with the API stopped:
     ```
     docker compose stop api worker
     psql -U disp_user -d postgres -c "ALTER DATABASE disp_db RENAME TO disp_broken;"
     psql -U disp_user -d postgres -c "ALTER DATABASE disp_restore_test RENAME TO disp_db;"
     docker compose start api worker
     ```

6. **Clean up** the scratch database once cut-over is confirmed good:
   ```
   psql -U disp_user -d postgres -c "DROP DATABASE disp_restore_test;"
   ```

7. **Reconcile files against the bucket.** Run `disp-admin files verify` before anything else touches
   `core.files`. It reports rows with no backing object and objects with no row, and **deletes
   nothing**. Rows without objects stay as they are (I3 in M18-files.md §2): they show up as broken
   links, never as silently vanished records. Objects without rows *will* be deleted by the next
   hourly sweep (I7) — if the restore is the thing that's wrong, mirror those objects aside first.

## Key rotation

| Key | Rotation impact | Procedure |
|---|---|---|
| `DISP_JWT_SECRET` | Every outstanding access token is instantly invalid; refresh cookies and PATs are unaffected (different secret space). Low blast radius. | Set the new value, restart the API. Users with an expired access token get a fresh one via their next `/api/auth/refresh` or PAT-authenticated call. |
| `DISP_SETTINGS_KEY` | Every previously-encrypted setting becomes undecryptable (`SettingsDecryptionError`, surfaced as `500 core.settings.decryption_failed`) — this is **not** a live re-encryption, it is data loss for existing rows. No HTTP endpoint reveals secret values in plaintext (`GET /api/settings/{domain}` always masks them, by design — §14.3). | Before rotating: run a one-off script, using the *old* key, that instantiates `SettingsStore(Fernet(old_key))` directly and calls `get_all(..., reveal_secrets=True)` for every (user, domain) pair to recover each plaintext value. Then rotate the env var, restart, and re-`PUT` each setting through the normal API so it gets re-encrypted under the new key. |
| Postgres credentials (`POSTGRES_PASSWORD`) | None to application data; only affects new connections. | Update the password in Postgres and in `.env`'s `DISP_DATABASE_URL`(`_SYNC`)/`POSTGRES_PASSWORD`, then restart `api` and `worker`. |
| `DISP_FILES_S3_ACCESS_KEY_ID` / `DISP_FILES_S3_SECRET_ACCESS_KEY` (R2 token) | None to stored files. Every outstanding file link is presigned with the token's secret, so **revoking the old token kills every outstanding link**; pages re-mint links on their next query refetch, and the web client retries a failed image once with a fresh link. | Create the new R2 token, set both values, `docker compose up -d api worker`, then revoke the old token in the R2 dashboard. |
| `DISP_LLM_API_KEY` / `DISP_EMBEDDING_API_KEY` | None to stored data — neither credential is ever persisted (§3). In-flight calls at the moment of restart fail and are recorded in `core.llm_call` with `outcome='unavailable'`; nothing is silently dropped. | Set the new value, `docker compose up -d api worker`. No re-encryption step, unlike `DISP_SETTINGS_KEY`. |
| `DISP_TRANSLATION_API_KEY` | None to stored data — never persisted (M22 §3). In-flight calls fail and are recorded in `core.translation_call` with `outcome='unavailable'`. | Set the new value, `docker compose up -d api worker`. **If the free/paid tier changed, clear or update `DISP_TRANSLATION_BASE_URL` in the same change** — see the host trap above; otherwise every call 403s with a message that looks like a bad key. |

Neither key rotation requires a database migration — both are purely environment-variable changes plus, for `DISP_SETTINGS_KEY`, the manual re-encryption pass described above.

## Rate limits (§17.6)

Enabled by default (`DISP_RATE_LIMIT_ENABLED=true` in production). A `429` response always carries a `Retry-After` header and `code=core.platform.rate_limited`. If legitimate traffic is being throttled, check `DISP_RATE_LIMIT_ENABLED` and the specific limiter hit (login: 5/minute per email; PAT creation: 20/hour per user; password change: 5/hour per user; default: 300/minute per remote address) before disabling rate limiting entirely.
