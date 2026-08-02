# M07 — Account, tokens, and admin screens

**Status:** Not started

**Scope:** `clients/web/src/routes/{_app.settings.account.tsx,_app.settings.tokens.tsx,
_app.admin.invites.tsx}`.

Covers TECHNICAL-SPEC-WEB.md §15 (Account, tokens, and admin screens) in full.

---

## §15.1 `/settings/account`

- Read-only display: display name, email, admin status, account creation date (from
  `GET /api/auth/me`, already fetched by M03's `AuthProvider` — reuse `qk.auth.me()`, don't
  refetch separately).
- **Change password** form: current password, new password, confirm, with `autocomplete`
  `current-password`/`new-password`. Client-side policy mirrors M03's §8.8 rules (≥12 chars, ≤128).
  Success → toast explaining other sessions were signed out (the backend revokes them; the caller's
  own session stays valid per backend §10.10 — confirm this against `docs/auth.md` if unclear) and
  the form resets. `422 auth.password_policy` → the backend's `detail` string rendered on the
  new-password field (per M02/M10's §7.3/§19.3 error-mapping machinery).
- Helper text notes the form is unavailable when signed in with a PAT — the browser client never
  authenticates with one (M03 §8.9), but the copy should state the backend's actual rule truthfully
  regardless, since a user could in principle be curious about it.

## §15.2 `/settings/tokens`

Manages PATs used by the `disp` CLI. **The browser never authenticates with these** — this screen
only lists/creates/revokes.

- Table: name, prefix, created, last used (relative, "Never" when null), expires ("Never" when
  null), Revoke action.
- **Create** dialog: name (required, ≤64 chars), optional expiry in days. Success → the plaintext
  token displayed **once**, in a dialog with a copy button, a "won't be shown again" warning, and an
  explicit "I've saved it" dismissal button (not just an X or Escape). The value:
  - MUST NOT be written to any store (no query cache entry holding it, no component state that
    outlives the dialog).
  - MUST NOT appear in the query cache after the dialog closes — if the create mutation's response
    is cached at all, strip the token field before it enters TanStack Query's cache, or don't cache
    the mutation response.
  - MUST be cleared from component state on unmount (a `useEffect` cleanup or equivalent, not
    reliance on garbage collection alone — assert this in a test, not by inspection).
- **Revoke** requires confirmation naming the specific token (not a generic "Are you sure?").
- Helper text: these are for the `disp` CLI, linking to the CLI docs (`docs/` in the repo root, or
  wherever `disp login`/`disp notes` are documented — cross-reference `README.md`'s quickstart rather
  than inventing a new doc path).

## §15.3 `/admin/invites`

Admin-only (M04's route guard already handles the `is_admin` check; this screen assumes it's only
reachable by an admin).

- Table: pending invites — email, created by, expires (relative), Revoke action.
- **Create** dialog: email (required), "Grant admin access" switch. Success → display the
  `accept_url` once with a copy button, copy explaining the system sends no email and the admin must
  deliver the link personally.
- `409 auth.user_exists` and `409 auth.invite_pending` → distinct messages on the email field
  (M02/M10's error-mapping machinery — two different codes, two different copy strings, both
  field-level not toast-level since the email field is the obvious home for either).
- The invite token/`accept_url` MUST NOT be logged or persisted beyond the one-time reveal dialog —
  same discipline as the PAT reveal above.

## Dependencies

- **M03** (`useAuth()`, `qk.auth.me()`), **M04** (route guards, page shell), **M02** (client/error
  mapping). Independent of M06 — these are hand-built screens, not schema-driven, so no dependency
  on `SchemaForm` or M00's backend amendments.

## Open questions / judgment calls for the implementer

- The spec doesn't say whether the tokens table paginates. Given the operating assumption of 1–20
  users each with a small number of PATs (§1.3), a single unpaginated table is a reasonable reading;
  don't build cursor pagination here speculatively — `GET /api/auth/tokens` should be checked against
  the actual backend route to confirm it doesn't already page before assuming a flat list is enough.
- Same question for `/admin/invites`'s pending-invite table — same reasoning applies.

## Verification

- Manual: create a token, confirm the plaintext appears once, close the dialog, reopen the tokens
  screen, confirm the plaintext is nowhere in the DOM, the TanStack Query devtools cache, or
  `localStorage`/`sessionStorage`.
- Manual: create an invite as admin, confirm `accept_url` follows through M03's `/accept-invite`
  flow end-to-end (this is the first milestone that can exercise that full loop, since M03 built the
  screen but had no way to generate a real invite token without this one).
- `422`/`409` error-mapping cases for password change and invite creation, per M02's table.
