# M10 — Forms, feedback, and accessibility hardening

**Status:** Complete

**Scope:** `clients/web/src/components/feedback/{ToastProvider,ErrorBoundary,EmptyState}.tsx`
(`OfflineBanner` was M09's), plus a cross-cutting pass over every form and screen built in
M03–M09: `react-hook-form` + Zod wiring, the `422`-to-field-error mapper (likely
`src/lib/mapValidationErrors.ts` or inline in `src/api/problem.ts`'s consumers), focus management,
and `eslint-plugin-jsx-a11y` enabled as an error-level lint rule (M01's `eslint.config.js`, amended
here).

Covers TECHNICAL-SPEC-WEB.md §19 (Forms and validation), §20 (Feedback, errors, and empty states),
§21 (Accessibility) — applied across every screen that exists by the time this milestone runs.

---

## Why this is a hardening pass, not a screen of its own

Unlike M05–M09, §19–21 don't describe a route or a component tree — they describe constraints that
apply to *every* form, toast, loading state, and interactive element already built. Treating this as
a dedicated milestone (rather than trusting each earlier milestone to self-apply these rules
perfectly under its own time pressure) mirrors how the backend's own milestone set handled
cross-cutting concerns — a dedicated pass catches drift that accumulates across several milestones
built by different sessions/people. Schedule this **after** M03–M09, not interleaved, precisely so
it can audit real, finished screens rather than a moving target.

## §19. Forms and validation

### §19.1 Library usage

`react-hook-form` with `zodResolver` everywhere a form exists (M03's login/accept-invite/password
forms, M06's `SchemaForm`, M07's create-token/create-invite dialogs, M08's note editor/create/share
dialogs). Uncontrolled inputs by default; controlled only where a Radix primitive requires it.

### §19.2 Client-side rules — every constraint mirrors a server constraint

| Field | Rule | Source |
|---|---|---|
| Email | non-empty, valid format, ≤254 | backend §10.4 |
| Password (new) | ≥12, ≤128, ≠ email | backend §10.3 |
| Display name | 1–100 | backend §6.2 |
| Note title | 0–200 (empty → `null`) | backend §18.2 |
| Note body | 1–20000 | backend §18.2 |
| Token name | 1–64 | backend §6.2 |
| Search `q` | ≤200 | backend §18.3 |

Audit every form built so far against this table — a mismatch (e.g. M08's note body accepting
20001 characters client-side before the server rejects it) is exactly the kind of drift this
milestone exists to catch.

### §19.3 Mapping `422` to fields — the algorithm every mutation's error handler uses

Backend returns `errors: [{loc, msg, type}]` where `loc` is e.g. `["body","email"]`. The client:

1. Drops a leading `"body"`, `"query"`, or `"path"` segment.
2. Joins the remainder with `.` to form the react-hook-form field name.
3. Calls `setError(fieldName, { message: msg })`.
4. If the field doesn't exist in the form, attaches the message to a form-level error region
   instead of silently discarding it.

This was referenced but not implemented by M02/M06/M07/M08 — build the shared helper here (or
confirm it was already factored out consistently) and make sure every screen's `422` handler calls
through the *same* function rather than five slightly-different inline implementations.

### §19.4 Behaviour

- Validate on blur and on submit; re-validate on change only after the first failed submit.
- Submit button disabled while submitting, **never** while merely invalid — disabling on invalid
  hides the reason for failure from the user, which is worse than letting them click and see the
  error.
- First invalid field receives focus on failed submit.
- Errors render below the field, `aria-describedby`-linked, field gets `aria-invalid="true"`.
- Destructive confirmations (delete note, revoke token, revoke invite) require a distinct confirm
  button labeled with the verb ("Delete note"), never "OK" — audit M07's revoke dialogs and M08's
  delete confirmation against this specifically, since a generic "OK" is an easy default to leave in
  place from a quick first pass.

## §20. Feedback, errors, and empty states

### §20.1 Toasts

Radix Toast, bottom-center mobile / bottom-right desktop, above the bottom nav (coordinate the
z-index/position with M04's `BottomNav`). Variants: success (4s), error (8s, dismissible, pauses on
hover/focus), info (5s). Max 3 concurrent, older collapse. `aria-live="polite"` for success/info,
`"assertive"` for errors. **Toasts must not be the sole channel for an error with a natural inline
home** — audit that every `422` (which has field homes) and every ACL/404 case (which has toast-vs-
inline rules per M02's §7.3 table) actually followed that table rather than defaulting to "just
toast it" as an easy fallback during the earlier milestones.

### §20.2 Error boundaries — three levels

1. **Root** — render crashes, full-page error, Reload + build version (`__APP_VERSION__`).
2. **Route** — per-route errors, shell/nav stay usable.
3. **Tile** — one per tile (M05 already built this; confirm it's actually wired, not just planned).

Every boundary logs to `console.error` and sends nothing anywhere — no telemetry, per §1.2's
explicit non-goal. Audit for any stray `console.log` left over from earlier milestones' development
— §25 acceptance criterion 24 forbids them in the shipped app.

### §20.3 Loading

- Route transitions: 2px indeterminate bar under TopBar, appearing only after 150ms (fast
  navigations shouldn't flash it).
- Lists/tiles: skeletons matching final layout dimensions (no layout shift).
- Buttons: inline spinner replaces the label's leading icon, label stays, **width doesn't change**.

### §20.4 Empty states

Every list and tile has a defined empty state: icon, one-line explanation, primary action button
where one makes sense. Copy from Appendix D. Audit M05 (dashboard empty), M08 (notes empty/
filtered-empty) against this — "no data" with no icon or explanation is explicitly forbidden.

## §21. Accessibility — WCAG 2.2 AA, requirements not aspirations

| # | Requirement |
|---|---|
| A1 | Contrast ≥4.5:1 body text, ≥3:1 large text/UI boundaries, both themes |
| A2 | Every interactive element keyboard-reachable, logical DOM order |
| A3 | Visible focus indicator: 2px outline, 2px offset, `--color-accent`. `outline: none` with no replacement is forbidden |
| A4 | Touch targets ≥44×44px (bottom-nav ≥56px tall) |
| A5 | Dialogs trap focus, close on Escape, restore focus to trigger, `role="dialog"` + `aria-labelledby` + `aria-modal="true"` — Radix provides this; don't override it |
| A6 | Every input has an associated `<label>`; placeholders are never labels |
| A7 | Icon-only buttons have `aria-label` |
| A8 | Status never conveyed by color alone (pinned notes: icon; active nav: filled icon; error fields: text) |
| A9 | Route changes move focus to `<h1>` and announce the new title via a visually-hidden `aria-live="polite"` region |
| A10 | "Skip to content" is the first focusable element |
| A11 | `prefers-reduced-motion: reduce` disables all non-essential animation |
| A12 | 200% page zoom and 200% text-only zoom: no content/function loss, no horizontal scroll below 320px |
| A13 | `<html lang="en">` |
| A14 | Loading regions `aria-busy`; skeletons `aria-hidden` + visually-hidden "Loading…" |
| A15 | Tile grid is `<ul>`/`<li>`; tiles are `<article>` with `aria-labelledby` pointing at their heading |

`eslint-plugin-jsx-a11y` MUST run with `recommended` config **as errors** (amend M01's
`eslint.config.js` here) — this turns A2/A6/A7-adjacent mistakes into build failures rather than
review-time catches. `@axe-core/playwright` scans (dashboard, notes list, note detail, settings,
login) are M11's automated layer; this milestone's job is to make those scans actually pass by
fixing what they find, not just to schedule them.

## Dependencies

Runs after **M03–M09** are functionally complete — this is a deliberate ordering choice (see
"Why this is a hardening pass" above), not a hard technical dependency in the sense of blocking
imports.

## Verification

- `pnpm lint` — `eslint-plugin-jsx-a11y` recommended-as-error passes with zero violations across the
  whole `src/` tree.
- Manual keyboard-only pass across dashboard, notes list, note detail, settings, login — every
  interactive element reachable in logical order, visible focus ring throughout.
- Manual `prefers-reduced-motion: reduce` + 200% zoom + 320px width spot-check on the same five
  screens.
- Full automated `@axe-core/playwright` scans are M11's to write and run in CI, but run one manually
  against each of the five key screens here before declaring this milestone done, so failures are
  caught before M11's suite is even assembled.
