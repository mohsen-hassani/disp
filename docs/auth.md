# Authentication

disp has three credential types. All three ultimately resolve to a `CurrentUser` via
`disp.core.auth.dependencies.current_user`, but they differ in format, lifetime, storage, and
what they can and can't do.

## Credential types

| | Access token (JWT) | Refresh token | Personal access token (PAT) |
|---|---|---|---|
| Format | `HS256` JWT, `Authorization: Bearer <jwt>` | `secrets.token_urlsafe(32)`, `disp_refresh` cookie only | `disp_pat_` + `secrets.token_urlsafe(32)`, `Authorization: Bearer <token>` |
| Lifetime | `MYSTUFF_ACCESS_TOKEN_TTL_SECONDS` (default 900s / 15 min) | `MYSTUFF_REFRESH_TOKEN_TTL_SECONDS` (default 30 days), rotated on every use | Indefinite by default, or `expires_in_days` at creation |
| Storage | Not stored — self-contained, verified by signature | `sha256(token)` in `core.sessions.refresh_token_hash` | `sha256(token)` in `core.api_tokens.token_hash` |
| Revocable before expiry? | **No** (see below) | Yes — the whole family | Yes — sets `revoked_at` |
| Can create a PAT? | Yes | N/A (never sent to `/api/auth/tokens`) | **No** — `403 auth.pat_cannot_mint` |
| Can change the password? | Yes | N/A | **No** — `403 auth.pat_insufficient` |

## The 15-minute access-token exposure window

Access tokens are JWTs verified purely by signature and expiry (`leeway=0`) — there is no
database lookup on the hot path, and consequently **no way to revoke one before it expires**.
This is an accepted tradeoff, not an oversight: revocation acts on the refresh-token family (see
below), and the maximum exposure from a stolen access token is bounded by
`MYSTUFF_ACCESS_TOKEN_TTL_SECONDS` — 15 minutes by default. If this window is too wide for a given
deployment, lower the TTL (as low as 60 seconds is accepted by `Settings`' validator) rather than
trying to add a revocation check to the hot path.

## Refresh rotation and reuse detection

Every login or `/api/auth/refresh` call issues a **new** refresh token and immediately invalidates
the one that was presented (if any) — this is rotation. All refresh tokens issued from the same
original login share a `family_id`.

If a refresh token is presented that has *already* been rotated (or revoked), this is treated as
a symptom of theft — the presented token was stolen and the legitimate client already rotated past
it, or vice versa. The server responds by revoking **every session in that family**, logging a
`WARNING` with `user_id` and `family_id`, and returning `401 auth.refresh_token_reused`. This
means a single successful theft-and-use of a stolen refresh token forces re-authentication on
every device sharing that login, not just the compromised one — a deliberate, conservative choice.

Refresh calls are cookie-authenticated (`disp_refresh`, `HttpOnly`), so they additionally require
the `X-Requested-With: disp` header as CSRF protection (§10.5) — a browser cross-site request
cannot set that header, so its absence is treated as `403 auth.csrf_required`.

## Personal access tokens (PATs)

PATs are the credential the `disp` CLI actually uses day to day: `disp login` exchanges a
password for a short-lived access token internally, immediately mints a PAT with that access
token, and discards the password and the access token — only the PAT is ever written to
`~/.config/disp/config.toml`. This is why every PAT-authenticated request has `auth_method ==
"api_token"`, and why the two restrictions above (`auth.pat_cannot_mint`, `auth.pat_insufficient`)
matter in practice: a leaked PAT (e.g. an exfiltrated CLI config file) cannot be used to mint a
longer-lived credential or lock the real owner out by changing their password.

## Adopting an external OIDC provider later

The auth subsystem is deliberately import-isolated (`disp.core.auth.__init__`'s public surface is
the only thing any other file — including modules — may depend on) specifically so that swapping
in an external OIDC provider is a change confined to `disp/core/auth/`. The stub at
`src/disp/core/auth/oidc.py` documents the intended path:

1. Fetch and cache the issuer's JWKS from OIDC discovery.
2. Validate the external token's signature, `iss`, `aud`, and `exp`.
3. Look up `core.users` by `(external_issuer, external_subject)` (columns that already exist on
   `User` for exactly this purpose — see `ck_users_external_pair` and `ck_users_has_credential`).
4. If no user matches, link by verified email on first login; otherwise reject.

The wiring point is a **fourth branch** in `dependencies.current_user`, taken when a presented
JWT's `iss` claim is not this application's own issuer (today, `current_user` only distinguishes
PAT vs. in-house JWT). No other file needs to change — routers, the CLI, and every module
continue calling the same `current_user`/`CurrentUser` names regardless of which branch resolved
the credential.
