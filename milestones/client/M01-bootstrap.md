# M01 — Bootstrap client scaffold

**Status:** Not started

**Scope:** `clients/web/{package.json,pnpm-lock.yaml,tsconfig.json,tsconfig.node.json,vite.config.ts,
tailwind.config.ts,eslint.config.js,.prettierrc,playwright.config.ts,vitest.config.ts,index.html,
openapi-ts.config.ts}`, `clients/web/public/{icons/,favicon.svg,offline.html}`,
`clients/web/src/{vite-env.d.ts,styles/index.css,lib/theme.ts,lib/cn.ts}`. The rest of `src/` is
created as empty directories per the tree in §5 and filled in by later milestones.

Covers TECHNICAL-SPEC-WEB.md §4 (Technology stack), §5 (Repository layout), §11.2–11.3 (design
tokens, theme bootstrap — the CSS only; components come in M04), §24.1–24.2 (configuration,
scripts).

---

## §4. Technology stack

`package.json` MUST pin every dependency at or above the **minimum** versions in §4's table (React
19, Vite 6, TypeScript 5.6, TanStack Router 1.87 / Query 5.62, `@hey-api/openapi-ts` 0.64,
Tailwind 4, the Radix primitives listed, `lucide-react` 0.460, `react-hook-form` 7.53, `zod` 3.23,
`vite-plugin-pwa` 0.21, Vitest 2.1, Testing Library, MSW 2.6, Playwright 1.49, ESLint +
typescript-eslint + `eslint-plugin-jsx-a11y`, Prettier 3.3). Commit `pnpm-lock.yaml`.

**Forbidden — must not appear in `package.json` at all:** Redux, MobX, Zustand (for server state —
a small React context for auth/theme is fine and lives in `src/auth/` and `src/lib/theme.ts`,
neither of which is "server state"), `axios`, `moment`, `date-fns`, any CSS-in-JS runtime, MUI/
Chakra/Ant, `@rjsf/core`.

## §5. Repository layout

Create exactly the tree in §5 under `clients/web/`. Two things worth flagging while scaffolding:

- `src/routeTree.gen.ts` and `src/api/generated/*` are generated files — create the directories but
  do not hand-write their contents; `main.tsx` (M04) and the API client (M02) populate them via
  their respective codegen commands.
- `tests/unit/`, `tests/mocks/`, `tests/e2e/` live at `clients/web/tests/`, sibling to `src/`, per
  the tree — not nested inside `src/`. Keep this distinction; several later milestones' test files
  depend on `tests/mocks/handlers.ts` being importable from both Vitest and Playwright configs.

## §24.1 Configuration — there is none

No `VITE_API_URL`, no `config.json` fetch, no runtime configuration mechanism of any kind. The only
build-time values are Vite's own `import.meta.env.MODE`/`import.meta.env.DEV` and one custom define,
`__APP_VERSION__`, sourced from `package.json`'s `version` field in `vite.config.ts`:

```ts
define: { __APP_VERSION__: JSON.stringify(pkg.version) }
```

This is a hard constraint, not a placeholder to fill in "for now" — §2.1 requires the client and API
to be same-origin with relative URLs (`/api/...`) always, so there is never a base-URL variable to
configure. Do not add one even as a documented escape hatch.

## §24.2 Scripts — exact `package.json["scripts"]` table

```json
{
  "dev":          "vite",
  "build":        "tsc -b && vite build",
  "preview":      "vite preview",
  "test":         "vitest run --coverage",
  "test:watch":   "vitest",
  "test:e2e":     "playwright test",
  "lint":         "eslint . && prettier --check .",
  "fmt":          "eslint . --fix && prettier --write .",
  "typecheck":    "tsc -b --noEmit",
  "api:generate": "openapi-ts",
  "api:check":    "openapi-ts && git diff --exit-code src/api/generated"
}
```

`eslint.config.js` MUST ignore `src/api/generated/` (M02 owns its contents) but TypeScript MUST
still type-check it — do not add it to `tsconfig`'s `exclude`.

## §11.2–11.3 Design tokens and theme bootstrap (CSS only — components in M04)

`src/styles/index.css` defines the full Appendix C token set as CSS custom properties, consumed via
Tailwind v4's `@theme` directive, for both `[data-theme="light"]` and `[data-theme="dark"]`. Copy
Appendix C's values verbatim — do not invent a palette; the spec states these specific pairs were
verified against the §21 A1 contrast requirement (4.5:1 body text, 3:1 large text/UI boundaries) and
substituting different hex values would silently break that guarantee.

`index.html` MUST include an inline theme-bootstrap script that reads a resolved theme (from
`localStorage`'s `disp.theme` key — see naming note below — falling back to
`prefers-color-scheme`) and sets `data-theme` on `<html>` **before first paint**, to avoid a flash of
the wrong theme. Per §24.3 (read ahead into M12's territory, but relevant to how this file is
authored now): this script must ultimately live in an external hashed file, not inline, because the
production CSP (`script-src 'self'`, no `'unsafe-inline'` for scripts) would otherwise block it.
Write it as `public/theme-bootstrap.js` (or equivalent build-time-hashed asset) from the start rather
than inline in `index.html`, so M12 doesn't have to retrofit it under CSP later.

`index.html` also sets the viewport meta exactly as §12.5 specifies
(`width=device-width, initial-scale=1, viewport-fit=cover`), `<html lang="en">` (§21 A13), and a
`<meta name="theme-color">` that M04's theme-switching logic updates at runtime.

## DISP naming applied here

- `package.json`'s `name` field: use `@disp/web` (or `disp-web` — pick one and keep it consistent
  with M12's Docker/Compose service naming, which uses `disp-web` for the container/router names).
- `index.html`'s `<title>` base string and `apple-mobile-web-app-title` (finalized in M09, but the
  static fallback `<title>` in `index.html` itself, before the router sets a per-route title, should
  read "DISP" not "MyStuff").
- The permitted `localStorage` keys (§8.1's table, relevant here only for the theme key since
  `disp.installDismissedAt` belongs to M09): **`disp.theme`**, not the spec's literal
  `mystuff.theme`. `src/lib/theme.ts` is the only file allowed to read/write this key.

## Dependencies

None — this is the foundational milestone. Everything else in `clients/web/` is built on top of the
tree and configs this milestone creates.

## Open questions / judgment calls for the implementer

- The spec doesn't say whether `pnpm-workspace.yaml` is needed since `clients/web/` is a subtree of
  a non-JS (Python) monorepo, not a JS monorepo root. It isn't — `clients/web/` can be a standalone
  pnpm project with its own lockfile; there's no other `package.json` anywhere else in the repo to
  workspace against. Don't add one.
- Icon assets (`public/icons/*.png`, `apple-touch-icon.png`) need actual pixel content, not just
  placeholder files — generate them from a single source SVG (the DISP mark) at build time or commit
  pre-rendered PNGs. Either is fine; just don't commit zero-byte placeholders that would make M09's
  Lighthouse PWA-installability check fail silently.

## Verification

- `pnpm install` succeeds from a clean checkout.
- `pnpm typecheck`, `pnpm lint` pass on the (still mostly empty) scaffold.
- `pnpm build` produces a `dist/` even before any route/component exists (a trivial `main.tsx`
  rendering nothing is enough at this stage — later milestones fill it in).
- Open `dist/index.html` directly (or via `pnpm preview`) and confirm the theme-bootstrap script
  sets `data-theme` before the page paints, with no visible flash, in both an OS-light and OS-dark
  environment.
