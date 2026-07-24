# Operations

## First deploy: migrations, schema, and the first admin

Migrations and schema application are explicit one-shot commands, never part of container
startup. The production image (`Dockerfile`) intentionally does **not** ship `uv` or the `./dev`
script — only the installed package and its console-script entry points (`alembic`, `disp-admin`,
`procrastinate`) — so run these directly rather than through `./dev migrate`:

```
docker compose run --rm api alembic --name=core upgrade head
docker compose run --rm api alembic --name=notes upgrade head
docker compose run --rm api procrastinate --app=disp.core.scheduler.app schema --apply
docker compose run --rm api disp-admin seed-admin --email you@example.com --display-name "You"
```

(Add one more `alembic --name=<branch> upgrade head` line per module with its own migration
branch, as modules are added — see `docs/adding-a-module.md`.) All three console scripts were
verified against a real Postgres 16 as part of writing this document.

## Health endpoints

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /health` | none | Overall status: database connectivity, discovered modules, worker last-seen timestamp. Returns `503` when the database is unreachable. |
| `GET /health/live` | none | Liveness probe — no database access. Always `200` if the process is up. Use this for container/orchestrator liveness checks; use `/health` for a real readiness signal. |

## Log locations

The API and worker both log structured JSON (or console-formatted text when `MYSTUFF_LOG_FORMAT=console`) to stdout/stderr — there is no log file on disk. Under `docker compose`, retrieve logs with:

```
docker compose logs -f api
docker compose logs -f worker
```

Every HTTP request log line includes `request_id`, which also appears in every `application/problem+json` error body's `request_id` field — use it to correlate a user-reported error with the corresponding log line. Refresh-token reuse (a potential credential-theft signal) logs at `WARNING` with `user_id` and `family_id`; treat repeated occurrences as worth investigating.

## Backups

`scripts/backup.sh` performs a nightly logical backup:

- `pg_dump -Fc` (custom/compressed format) to `$BACKUP_DIR/disp-<UTC timestamp>.dump` (default `BACKUP_DIR=/var/backups/disp`).
- Retention: the 7 most recent daily dumps, plus one dump per week for 4 further weeks. Everything older is pruned.
- If `BACKUP_REMOTE` is set (an `s3://...` URI or an `rsync`-style `user@host:/path`), the fresh dump is copied off-host immediately after the local dump completes.

Run it nightly via cron, e.g.:

```cron
0 3 * * * cd /opt/disp && MYSTUFF_DATABASE_URL_SYNC=... BACKUP_REMOTE=s3://my-bucket/disp-backups/ ./scripts/backup.sh >> /var/log/disp-backup.log 2>&1
```

**Prerequisite:** the host running `backup.sh` needs a `pg_dump`/`pg_restore` client whose major version is **at least** the Postgres server's (16). A mismatched client refuses to run (`pg_dump: error: server version: 16.14; pg_dump version: 14.21 ... aborting because of server version mismatch`) — this was hit and fixed during verification of this exact document, by running `pg_dump` inside the `postgres:16-alpine` container itself rather than relying on the host's client. In production, run the backup from a container built on the same Postgres image (or install a matching `postgresql-client-16` package on the backup host).

### ⚠️ `MYSTUFF_SETTINGS_KEY` needs its own backup

`pg_dump` backs up the **database**, not the environment. `core.settings.value_encrypted` is Fernet-encrypted with `MYSTUFF_SETTINGS_KEY`, which lives only in the environment (S11) — it is never stored in the database. **If `MYSTUFF_SETTINGS_KEY` is lost, every encrypted setting (currently: notification-channel Apprise URLs) becomes permanently unrecoverable, even with a perfect database restore.** Back this key up separately, in a secrets manager or an offline copy — not alongside the `pg_dump` output.

By contrast, losing `MYSTUFF_JWT_SECRET` is low-severity: it only invalidates every outstanding access token (users re-authenticate via their still-valid refresh cookie or PAT) and does not affect any stored data.

### Restore procedure (verified)

This procedure was executed against a real dump of the dev database as part of writing this document — not just written from the spec. Commands and output below are the actual verified run (against `postgres:16-alpine` in a local container; identical against production, modulo container/host names).

1. **Take or locate a dump:**

   ```
   $ docker exec disp-postgres-dev pg_dump -Fc -U disp -d disp -f /tmp/disp-test.dump
   ```

2. **Create an empty target database** (never restore over the live one directly — see step 4):

   ```
   $ docker exec disp-postgres-dev psql -U disp -d postgres -c "CREATE DATABASE disp_restore_test OWNER disp;"
   CREATE DATABASE
   ```

3. **Restore the dump:**

   ```
   $ docker exec disp-postgres-dev pg_restore -U disp -d disp_restore_test /tmp/disp-test.dump
   ```

   (No output on success — `pg_restore` is silent unless something fails.)

4. **Verify the restore before cutting over.** At minimum, confirm the expected tables exist and row counts are sane:

   ```
   $ docker exec disp-postgres-dev psql -U disp -d disp_restore_test -c "\dt core.*"
                  List of relations
    Schema |         Name         | Type  | Owner
   --------+----------------------+-------+-------
    core   | acl                  | table | disp
    core   | alembic_version_core | table | disp
    core   | api_tokens           | table | disp
    core   | invites              | table | disp
    core   | notification_log     | table | disp
    core   | sessions             | table | disp
    core   | settings             | table | disp
    core   | users                | table | disp
   (8 rows)

   $ docker exec disp-postgres-dev psql -U disp -d disp_restore_test -tAc "SELECT count(*) FROM core.users;"
   1
   ```

   Compare the row count against the source database (`psql -d disp -tAc "SELECT count(*) FROM core.users;"`) — it matched exactly in this verification run.

5. **Cut over.** Once verified, either:
   - Point `MYSTUFF_DATABASE_URL` at the restored database and restart the API/worker, or
   - Rename the live (broken) database aside and rename the restored one into its place, inside a maintenance window with the API stopped:
     ```
     docker compose stop api worker
     psql -U disp -d postgres -c "ALTER DATABASE disp RENAME TO disp_broken;"
     psql -U disp -d postgres -c "ALTER DATABASE disp_restore_test RENAME TO disp;"
     docker compose start api worker
     ```

6. **Clean up** the scratch database once cut-over is confirmed good:
   ```
   psql -U disp -d postgres -c "DROP DATABASE disp_restore_test;"
   ```

## Key rotation

| Key | Rotation impact | Procedure |
|---|---|---|
| `MYSTUFF_JWT_SECRET` | Every outstanding access token is instantly invalid; refresh cookies and PATs are unaffected (different secret space). Low blast radius. | Set the new value, restart the API. Users with an expired access token get a fresh one via their next `/api/auth/refresh` or PAT-authenticated call. |
| `MYSTUFF_SETTINGS_KEY` | Every previously-encrypted setting becomes undecryptable (`SettingsDecryptionError`, surfaced as `500 settings.decryption_failed`) — this is **not** a live re-encryption, it is data loss for existing rows. No HTTP endpoint reveals secret values in plaintext (`GET /api/settings/{domain}` always masks them, by design — §14.3). | Before rotating: run a one-off script, using the *old* key, that instantiates `SettingsStore(Fernet(old_key))` directly and calls `get_all(..., reveal_secrets=True)` for every (user, domain) pair to recover each plaintext value. Then rotate the env var, restart, and re-`PUT` each setting through the normal API so it gets re-encrypted under the new key. |
| Postgres credentials (`POSTGRES_PASSWORD`) | None to application data; only affects new connections. | Update the password in Postgres and in `.env`'s `MYSTUFF_DATABASE_URL`(`_SYNC`)/`POSTGRES_PASSWORD`, then restart `api` and `worker`. |

Neither key rotation requires a database migration — both are purely environment-variable changes plus, for `MYSTUFF_SETTINGS_KEY`, the manual re-encryption pass described above.

## Rate limits (§17.6)

Enabled by default (`MYSTUFF_RATE_LIMIT_ENABLED=true` in production). A `429` response always carries a `Retry-After` header and `code=rate_limited`. If legitimate traffic is being throttled, check `MYSTUFF_RATE_LIMIT_ENABLED` and the specific limiter hit (login: 5/minute per email; PAT creation: 20/hour per user; password change: 5/hour per user; default: 300/minute per remote address) before disabling rate limiting entirely.
