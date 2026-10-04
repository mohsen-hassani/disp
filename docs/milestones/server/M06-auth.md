# M6 — Auth subsystem

**Status:** Complete

**Scope:** `auth/passwords.py`, `auth/tokens.py`, `auth/acl.py`, `auth/sessions.py`, `auth/dependencies.py`, `auth/invites.py`, `auth/schemas.py`, `auth/routes.py`, `auth/oidc.py`, `auth/__init__.py` (public surface), plus `tests/core/test_boundaries.py` (written and verified against injected violations).

Covers TECHNICAL-SPEC.md §10 (Auth subsystem) and §11 (Authorization/ACL — `acl.py` lives under `auth/` per the repo tree, so it was built here).

---

## §10.1 Public surface (architectural constraint)

`src/disp/core/auth/__init__.py` MUST contain exactly:

```python
from disp.core.auth.acl import Permission, can
from disp.core.auth.dependencies import CurrentUser, current_user, require_admin

__all__ = ["CurrentUser", "Permission", "can", "current_user", "require_admin"]
```

**No module under `disp/modules/` may import any other name from `disp.core.auth` or from any of its submodules.** This is enforced by an automated test (§22.5). Violating it is a build failure, not a style issue. This constraint is what makes replacing in-app auth with an external OIDC provider a change confined to `disp/core/auth/`.

## §10.2 `CurrentUser`

```python
@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: UUID
    email: str
    display_name: str
    is_admin: bool
    auth_method: Literal["access_token", "api_token"]
    token_id: UUID | None  # api_tokens.id when auth_method == "api_token"
```

## §10.3 Passwords

`passwords.py` MUST expose:

```python
def hash_password(plain: str) -> str
def verify_password(plain: str, hashed: str) -> bool
def validate_password_policy(plain: str, *, email: str) -> None   # raises PasswordPolicyError
```

Requirements:

- Hashing uses `pwdlib.PasswordHash.recommended()` (Argon2id).
- Policy: length ≥ 12 and ≤ 128; MUST NOT equal the email address case-insensitively; MUST NOT be one of the 100 most common passwords, supplied as a committed constant list in `passwords.py`. No composition rules (no forced symbols/digits).
- `verify_password` MUST return `False` rather than raise on a malformed hash.
- A module-level constant `DUMMY_HASH` MUST hold a pre-computed Argon2id hash of a random string, used for timing equalisation (§10.4).

## §10.4 Login

**`POST /api/auth/login`**

Request (`application/json`):
```json
{"email": "a@b.com", "password": "correct horse battery staple", "device_label": "firefox-laptop"}
```
`device_label` is optional, max 64 chars.

Algorithm (order is normative):

1. Look up the user by `lower(email)`.
2. If not found: call `verify_password(password, DUMMY_HASH)` and discard the result, then return `401 auth.invalid_credentials`.
3. If found but `is_active` is false: still perform the verify, then return `403 auth.account_disabled`.
4. If `password_hash` is NULL: return `401 auth.invalid_credentials`.
5. Verify. On failure return `401 auth.invalid_credentials`.
6. Create a session: new `family_id = uuid4()`, refresh token per §10.5, `expires_at = now + REFRESH_TOKEN_TTL`, record `user_agent` (truncated to 256 chars) and `ip_address` from `X-Forwarded-For` (first hop) or the peer address.
7. Issue an access JWT per §10.6.

Responses:

| Status | Body |
|---|---|
| `200` | `{"access_token": "...", "token_type": "bearer", "expires_in": 900, "user": {UserOut}}` |
| `401` | problem, `code=auth.invalid_credentials` |
| `403` | problem, `code=auth.account_disabled` |
| `422` | validation problem |
| `429` | problem, `code=rate_limited` |

`200` MUST also set:

```
Set-Cookie: disp_refresh=<token>; Path=/api/auth; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000
```

`Secure` is omitted only when `DISP_COOKIE_SECURE` is false. `Domain` is set only when configured.

The error message text for `auth.invalid_credentials` MUST be identical for unknown-email and wrong-password cases.

## §10.5 Refresh tokens and rotation

- Format: `secrets.token_urlsafe(32)` (43 characters). Opaque; no structure.
- Stored as `sha256(token).hexdigest()` in `sessions.refresh_token_hash`. The plaintext is never persisted or logged.
- A `family_id` groups every token descended from one login.

**`POST /api/auth/refresh`**

- Reads the token from the `disp_refresh` cookie. It MUST NOT accept the token from a request body or header.
- MUST require the header `X-Requested-With: disp`; absence returns `403 auth.csrf_required`. This is the CSRF defence, since the endpoint is cookie-authenticated.

Algorithm:

1. Hash the presented token; look up the session.
2. Not found → `401 auth.invalid_refresh_token`.
3. `revoked_at IS NOT NULL` **or** `rotated_at IS NOT NULL` → **reuse detected**: revoke every session in the same `family_id` (set `revoked_at = now()`, `revoked_reason = 'reuse_detected'`), log at `WARNING` with `user_id` and `family_id`, clear the cookie, return `401 auth.refresh_token_reused`.
4. `expires_at < now()` → mark `revoked_reason='expired'`, return `401 auth.refresh_token_expired`.
5. User inactive → `403 auth.account_disabled`.
6. Otherwise rotate: create a new session row with the same `family_id`, `previous_session_id` set to the current row; set the current row's `rotated_at = now()`, `revoked_at = now()`, `revoked_reason='rotation'`. Issue a new access token and set a new cookie.

Steps 1–6 MUST run inside a single transaction with `SELECT … FOR UPDATE` on the session row.

Response `200`: same shape as login. Errors clear the cookie with `Max-Age=0`.

**`POST /api/auth/logout`** — requires the cookie and `X-Requested-With`. Revokes the whole `family_id` with reason `logout`, clears the cookie, returns `204`. Returns `204` even when the cookie is absent or unknown (no information leak).

## §10.6 Access tokens

- Algorithm `HS256`, secret `DISP_JWT_SECRET`.
- Claims: `sub` (user id, string UUID), `iat`, `exp`, `jti` (uuid4), `typ` = `"access"`, `email`, `adm` (bool).
- TTL from `DISP_ACCESS_TOKEN_TTL_SECONDS`.
- Verification MUST enforce `typ == "access"`, signature, and expiry with `leeway=0`.
- Access tokens are **not** revocable before expiry. This is accepted: revocation acts on the refresh family, and 15 minutes is the maximum exposure. This MUST be stated in `docs/auth.md` (M16).

## §10.7 Personal access tokens

- Format: `disp_pat_` + `secrets.token_urlsafe(32)`.
- `token_hash` = `sha256(full_token).hexdigest()`.
- `token_prefix` = the brand prefix + 8 more characters of the random suffix, stored for display.
- The plaintext is returned **once**, in the creation response only. It is never retrievable again and never logged.

> **Note on the spec's literal numbers:** §10.7 originally said "Total length 53" and "first 18 characters (`disp_pat_` + 8)". Both numbers were computed against the spec's older `disp_pat_` prefix (10 chars: 10+43=53, 10+8=18). With the resolved `disp_pat_` prefix (9 chars), the actual total is 52 and the display prefix is 17 chars (`len(PAT_PREFIX) + 8`, computed dynamically rather than hardcoded) — the *behavioral* rule ("prefix + 8 more characters") is preserved; only the stale arithmetic annotations are not.

Endpoints:

| Method | Path | Auth | Behaviour |
|---|---|---|---|
| `GET` | `/api/auth/tokens` | any | Lists the caller's non-revoked tokens: `id`, `name`, `token_prefix`, `created_at`, `last_used_at`, `expires_at` |
| `POST` | `/api/auth/tokens` | **access_token only** | Creates a token. Body: `{"name": str, "expires_in_days": int \| null}`. Returns `201` with the plaintext in field `token`. |
| `DELETE` | `/api/auth/tokens/{id}` | any | Sets `revoked_at`. `204`. `404` if not the caller's. |

**A PAT MUST NOT be usable to create another PAT.** `POST /api/auth/tokens` MUST reject `auth_method == "api_token"` with `403 auth.pat_cannot_mint`. This prevents a leaked token from minting persistence.

`last_used_at` MUST be updated on successful authentication, but at most once per 60 seconds per token (compare before writing) to avoid a write on every request.

> **Implementation note:** the 404-on-not-found-or-not-caller's case for `DELETE /api/auth/tokens/{id}` has no dedicated code in Appendix A. Added `auth.token_not_found`, following the exact naming pattern of `notes.not_found`/`notes.user_not_found` — a minor, unavoidable gap-fill (Appendix A enumerates codes but doesn't cover every endpoint's error paths).

## §10.8 The `current_user` dependency

Signature:

```python
async def current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser
```

Resolution:

1. No `Authorization` header → `401 auth.missing_credentials`, response includes `WWW-Authenticate: Bearer`.
2. Header not matching `^Bearer (.+)$` → `401 auth.malformed_credentials`.
3. Credential starts with `disp_pat_` → PAT path: hash, look up, reject if `revoked_at` set (`401 auth.token_revoked`) or `expires_at` past (`401 auth.token_expired`); load user; reject inactive (`403 auth.account_disabled`); update `last_used_at` subject to the 60-second rule; return `CurrentUser(auth_method="api_token", token_id=...)`.
4. Otherwise JWT path: decode and validate; on any `PyJWTError` → `401 auth.invalid_token`; expired → `401 auth.token_expired`; load user by `sub`; missing → `401 auth.invalid_token`; inactive → `403 auth.account_disabled`; return `CurrentUser(auth_method="access_token", token_id=None)`.

The refresh cookie MUST NOT authenticate any endpoint other than `/api/auth/refresh` and `/api/auth/logout`.

`require_admin` wraps `current_user` and raises `403 auth.admin_required` when `is_admin` is false.

## §10.9 Invites

**`POST /api/auth/invites`** — admin only. Body `{"email": str, "is_admin": bool = false}`.

- Rejects an email that already belongs to a user (`409 auth.user_exists`).
- Rejects a second pending invite for the same email (`409 auth.invite_pending`) — enforced by `uq_invites_pending_email`.
- Token: `secrets.token_urlsafe(32)`, stored hashed.
- Returns `201` with `{"id", "email", "token", "accept_url", "expires_at"}` where `accept_url = f"{DISP_BASE_URL}/accept-invite?token={token}"`. The plaintext token appears only here. Delivery to the invitee is the admin's problem; the system sends no email.

**`GET /api/auth/invites`** — admin only. Lists pending invites without tokens.

**`DELETE /api/auth/invites/{id}`** — admin only. Hard-deletes a pending invite. `204`.

**`POST /api/auth/accept-invite`** — unauthenticated. Body `{"token", "display_name", "password"}`.

1. Hash and look up. Not found → `404 auth.invite_not_found`.
2. `accepted_at` set → `409 auth.invite_used`.
3. `expires_at` past → `410 auth.invite_expired`.
4. Validate the password policy → `422 auth.password_policy` with the specific reason in `detail`.
5. If a user with that email now exists → `409 auth.user_exists`.
6. Create the user with `is_admin` from the invite; mark the invite accepted; create a session and issue tokens exactly as login does.
7. Return `201` with the login response body and the refresh cookie.

Steps 1–6 run in one transaction.

## §10.10 Password change and the OIDC stub

**`POST /api/auth/password`** — authenticated, **access_token only** (`403 auth.pat_insufficient` for PATs). Body `{"current_password", "new_password"}`. Verifies the current password, validates the new one, rehashes, then revokes **all** sessions for the user except the caller's current family, with reason `password_change`. Returns `204`.

> **Implementation note:** a JWT carries no session/family reference (stateless), so "the caller's current family" is resolved by reading the `disp_refresh` cookie if present on the same request (browser client sends both) and looking up its family; if absent, all sessions are revoked. This is the only sane mechanism given JWTs carry no session linkage.

**`GET /api/auth/me`** — returns `UserOut` plus `auth_method`.

`src/disp/core/auth/oidc.py` MUST exist and MUST contain a documented stub:

```python
async def resolve_external_token(token: str, session: AsyncSession) -> CurrentUser:
    """Reserved for a future external OIDC provider.

    Planned implementation:
      1. Fetch and cache the issuer's JWKS from OIDC discovery.
      2. Validate signature, `iss`, `aud`, and `exp`.
      3. Look up core.users by (external_issuer, external_subject).
      4. If absent, link by verified email on first login; otherwise 403.

    Wiring point: a fourth branch in `dependencies.current_user`, taken when
    the JWT's `iss` claim is not this application. No other file changes.
    """
    raise NotImplementedError("External OIDC is not enabled in this deployment.")
```

It MUST NOT be called from anywhere. A test asserts it raises `NotImplementedError`.

## §10.11 Admin bootstrap

Covered in M11 (`disp-admin seed-admin`), not here.

## §11. Authorization (ACL)

### 11.1 Model

```python
class Permission(StrEnum):
    READ = "read"
    WRITE = "write"
    OWNER = "owner"


_RANK = {Permission.READ: 1, Permission.WRITE: 2, Permission.OWNER: 3}

ACTION_REQUIRES: dict[str, Permission] = {
    "read": Permission.READ,
    "list": Permission.READ,
    "create": Permission.WRITE,
    "update": Permission.WRITE,
    "delete": Permission.WRITE,
    "share": Permission.OWNER,
    "unshare": Permission.OWNER,
    "transfer": Permission.OWNER,
}
```

### 11.2 API

```python
async def can(session, user: CurrentUser, action: str,
              resource_type: str, resource_id: str | UUID) -> bool
async def require(session, user, action, resource_type, resource_id) -> None   # raises 403
async def grant(session, *, resource_type, resource_id, user_id,
                permission: Permission, granted_by: UUID) -> None
async def revoke(session, *, resource_type, resource_id, user_id) -> None
async def list_grants(session, *, resource_type, resource_id) -> list[Grant]
async def readable_ids(session, *, user_id, resource_type) -> list[str]
```

Semantics:

- `can` returns `True` when a row exists for `(resource_type, resource_id, user_id)` whose permission rank ≥ the rank required by `action`.
- An unknown `action` raises `ValueError` — it is a programming error, not a denial.
- `can` performs **no implicit ownership inference**. A module that creates a resource MUST call `grant(..., permission=OWNER)` in the same transaction. Failing to do so leaves the resource inaccessible; this is intentional and MUST be covered by a test.
- Admin users are **not** implicitly granted access to other users' resources. `is_admin` governs invite management only.
- `readable_ids` exists so modules can filter list queries without N+1 permission checks.

## §22.5 The boundary test (written in this milestone)

`tests/core/test_boundaries.py` MUST parse every `.py` file under `src/disp/modules/` with `ast`, collect all `ImportFrom` and `Import` nodes referencing `disp.core.auth`, and assert that the only imported names are `CurrentUser`, `Permission`, `can`, `current_user`, `require_admin`, and that no submodule (`disp.core.auth.tokens`, etc.) is imported at all. The failure message MUST name the offending file, line, and symbol.

A second assertion in the same file: no file under `src/disp/modules/` imports `disp.core.app`, `disp.core.db.engine`, or another module's package (`disp.modules.<other>`).

> **Implementation note:** since `disp.core.db` has no literal `engine` symbol (only a `create_engine()` factory), this was interpreted as: ban `create_engine`/`create_session_maker`/`Base`/`metadata` from `disp.core.db`, while allowing `get_session`/`session_scope` (the sanctioned per-request/per-task accessors — analogous to how `get_session` is exactly the kind of narrow, safe accessor §10.1 already sanctions for auth). Verified by temporarily injecting a violating file and confirming both tests fail with correct file:line:symbol messages, then removing it.

## Retroactive amendment (made during M13)

§10.1's literal `auth/__init__.py` code block exports only `{CurrentUser, Permission, can, current_user, require_admin}` — but §18.3 explicitly requires the **notes module itself** to call `grant(...)` (on note creation, in the same transaction as the insert) and to filter its list query using `readable_ids`, neither of which is in that export list. This is a genuine contradiction, not just an underspecified detail: G4 ("per-resource sharing authorization ... usable by any module") and §11.2's full ACL API (`can`, `require`, `grant`, `revoke`, `list_grants`, `readable_ids`) only make sense if modules can reach the whole ACL surface, and the boundary's own stated rationale — "makes replacing in-app auth with an external OIDC provider a change confined to `disp/core/auth/`" — is specifically about *authentication* (how a caller's identity is resolved), which has nothing to do with `acl.py`; swapping in OIDC would never touch grant/revoke/readable_ids.

Resolved by expanding `auth/__init__.py` to export the full ACL API (`Permission, can, require, grant, revoke, list_grants, readable_ids`) alongside the three auth-proper names (`CurrentUser, current_user, require_admin`), and updating `test_boundaries.py`'s `ALLOWED_AUTH_NAMES` to match. `dependencies.py`'s `optional_user` and every auth-only submodule (`tokens`, `sessions`, `passwords`, `invites`, `schemas`, `routes`, `oidc`) remain off-limits to modules, unchanged. Re-ran the boundary test (still passes) and the full suite after the change.

## Second retroactive amendment (also during M13): `Base` is not "the engine"

The same M6 boundary test also banned every name from `disp.core.db` except `get_session`/`session_scope`, on the reasoning that `Base`/`metadata`/`create_engine`/`create_session_maker` were all "the SQLAlchemy engine" §8.4 forbids modules from importing. That was too broad: writing `notes/models.py` (M13) immediately failed the boundary test on `from disp.core.db import Base` — but every module MUST inherit from the same shared declarative `Base` to define ORM models at all (per the M5 design: one shared `Base`/`MetaData` across every schema, filtered per branch by alembic's `include_object` hook). There is no way to define a module's tables without it.

Re-read literally, §8.4 bans "the SQLAlchemy engine" specifically — i.e. `create_engine`/`create_session_maker`, which would let a module construct its own raw, unmanaged connection pool, bypassing the platform's request/task session pattern. `Base` is a declarative-mapping building block, not an engine. Resolved by adding `Base` to `test_boundaries.py`'s `ALLOWED_DB_NAMES` (now `{get_session, session_scope, Base}`); `metadata`/`create_engine`/`create_session_maker` remain banned. Re-ran both boundary tests (pass) and the full suite after the change.
