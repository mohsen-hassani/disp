# M1 — Core primitives (config, errors, logging, pagination)

**Status:** Complete

**Scope:** `core/config.py` (`Settings`, `get_settings`), `core/errors.py` (`ProblemDetail`, `AppError` hierarchy, exception handlers), `core/logging.py` (structlog + `RequestIdMiddleware`), `core/pagination.py` (cursor codec, `Page` model), plus `tests/core/test_pagination.py` and `tests/core/test_errors.py`.

Covers TECHNICAL-SPEC.md §5 (Configuration), §17.3–§17.4 (error envelope, exception handlers), §17.5 (pagination), §20 (logging, partial — health endpoint itself is M10).

---

## §5. Configuration

All configuration is read from environment variables via `pydantic-settings`. Prefix: `DISP_`. `.env` is loaded in development only.

### 5.1 Settings model

`src/disp/core/config.py` MUST define:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DISP_", env_file=".env", extra="forbid")
```

### 5.2 Variable registry

| Variable | Type | Required | Default | Validation |
|---|---|---|---|---|
| `DISP_DATABASE_URL` | str | yes | — | MUST start with `postgresql+asyncpg://` |
| `DISP_DATABASE_URL_SYNC` | str | no | derived | Derived from above by replacing `+asyncpg` with `+psycopg`; used by Alembic and Procrastinate |
| `DISP_JWT_SECRET` | SecretStr | yes | — | MUST be ≥ 32 characters; startup fails otherwise |
| `DISP_SETTINGS_KEY` | SecretStr | yes | — | MUST be a valid urlsafe-base64 32-byte Fernet key |
| `DISP_ACCESS_TOKEN_TTL_SECONDS` | int | no | `900` | 60–3600 |
| `DISP_REFRESH_TOKEN_TTL_SECONDS` | int | no | `2592000` (30 d) | 3600–7776000 |
| `DISP_INVITE_TTL_SECONDS` | int | no | `604800` (7 d) | 3600–2592000 |
| `DISP_PAT_DEFAULT_TTL_DAYS` | int \| None | no | `None` (no expiry) | ≥ 1 if set |
| `DISP_MODULES` | str | no | `""` | Comma-separated allow-list of module domains. Empty = load all discovered. |
| `DISP_BASE_URL` | str | yes | — | Public URL, e.g. `https://disp.example.com`. Used to build invite links. No trailing slash. |
| `DISP_CORS_ORIGINS` | str | no | `""` | Comma-separated origins |
| `DISP_COOKIE_SECURE` | bool | no | `true` | MUST be `true` in production |
| `DISP_COOKIE_DOMAIN` | str \| None | no | `None` | |
| `DISP_LOG_LEVEL` | str | no | `INFO` | One of DEBUG/INFO/WARNING/ERROR |
| `DISP_LOG_FORMAT` | str | no | `json` | `json` or `console` |
| `DISP_DAILY_PLANNER_CRON` | str | no | `0 6 * * *` | 5-field cron |
| `DISP_TIMEZONE` | str | no | `Europe/Amsterdam` | IANA name; used for "today" boundaries |
| `DISP_RATE_LIMIT_ENABLED` | bool | no | `true` | |
| `DISP_ENV` | str | no | `production` | `production` \| `development` \| `test` |

`get_settings()` MUST be `@lru_cache`-decorated and MUST be the only way settings are obtained.

### 5.3 Startup validation

On boot the application MUST fail fast (log a fatal error, exit code 1) if:
- any required variable is missing;
- `JWT_SECRET` is shorter than 32 characters;
- `SETTINGS_KEY` is not a valid Fernet key;
- `DISP_ENV == "production"` and `COOKIE_SECURE` is false;
- the database is unreachable after 5 retries with 2-second backoff (the DB-reachability check happens in `app.py`/`db.py`, wired at M10).

### 5.4 `.env.example`

MUST be committed, MUST list every variable in §5.2 with placeholder values, and MUST include a comment showing how to generate secrets:

```
# python -c "import secrets; print(secrets.token_urlsafe(48))"
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## §17.3 Error envelope

All errors use RFC 9457 `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Invalid credentials",
  "status": 401,
  "detail": "The email or password is incorrect.",
  "instance": "/api/auth/login",
  "code": "auth.invalid_credentials",
  "request_id": "01JF3K…"
}
```

`code` is machine-readable and drawn from Appendix A. `detail` is human-readable and MUST NOT contain secrets, hashes, SQL, or stack traces.

`422` responses add `errors`: a list of `{"loc": [...], "msg": "...", "type": "..."}`.

## §17.4 Exception handlers

`create_app` MUST register handlers for: `AppError` (the project's base class carrying `status`, `code`, `title`, `detail`), `RequestValidationError`, `HTTPException`, and `Exception`. The catch-all handler logs the full traceback at `ERROR` with the request id and returns a generic `500 internal_error` whose `detail` is `"An unexpected error occurred."` — never the exception text.

(Implementation note: a `RateLimitExceeded` handler was also added here, per §17.6's 429/Retry-After requirement — not explicitly listed in this section but required by the rate-limiting table.)

## §17.5 Pagination

Cursor-based. Query parameters `limit` (default 20, min 1, max 100) and `cursor` (opaque).

The cursor is `base64url(json.dumps({"ts": <iso8601>, "id": "<uuid>"}))`, encoding the sort key of the last returned item. Decoding failure → `400 pagination.invalid_cursor`.

Response envelope for every list endpoint:

```json
{"items": [...], "next_cursor": "eyJ0cyI6…", "has_more": true}
```

`next_cursor` is `null` when `has_more` is false. Total counts are not provided.

## §20. Logging and observability (primitives covered here; health endpoint is M10)

- `structlog` with a JSON renderer when `DISP_LOG_FORMAT=json`, Rich console renderer otherwise.
- Standard-library logging is routed through structlog; uvicorn access logs are disabled in favour of the middleware below.
- Every log record carries: `timestamp` (ISO 8601 UTC), `level`, `event`, `logger`, and, when available, `request_id`, `user_id`, `module`.
- `RequestIdMiddleware` reads `X-Request-ID` or generates a UUID4, binds it to the structlog context, and echoes it in the response header.
- One `INFO` line per request: `event="http_request"`, `method`, `path`, `status`, `duration_ms`, `user_id`.
- One `INFO` line per task execution: `event="task_completed"`, `task`, `job_id`, `duration_ms`, `attempt`.
- **Never logged:** passwords, password hashes, refresh tokens, PAT plaintexts, Apprise URLs, `Authorization` header values, cookie values, `DISP_JWT_SECRET`, `DISP_SETTINGS_KEY`. A test asserts these strings do not appear in captured log output for the login and notifier paths.
