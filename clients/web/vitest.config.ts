import { defineConfig, mergeConfig } from 'vitest/config';

import viteConfig from './vite.config';

// WEB-SPEC §23.1/§23.2: Vitest + RTL + MSW own the unit/component layer;
// Playwright (playwright.config.ts) owns e2e. Coverage gates below (≥80%
// lines overall, ≥95% on src/auth/ and src/components/schema-form/) are the
// real, enforced thresholds as of M11 — mirrors how the backend's own gate
// (`≥85% overall, ≥95% on core/auth/`, per CLAUDE.md) is treated: a build
// failure, not aspirational. Gated on `lines` only, matching §23.1's own
// literal wording and the backend's precedent of using line coverage as the
// metric that matters.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      // Matches the `http://localhost` baseUrl every test file's own
      // `client.setConfig({ baseUrl: 'http://localhost' })` uses (see M02's
      // client.test.ts) — MSW (§23.2) resolves a handler's relative URL
      // pattern against `document.location`, so a mismatched default jsdom
      // origin (jsdom's own default is `http://localhost:3000`) makes every
      // MSW handler silently fail to match a request built against the
      // baseUrl the rest of the suite already standardizes on.
      environmentOptions: { jsdom: { url: 'http://localhost/' } },
      include: ['tests/unit/**/*.{test,spec}.{ts,tsx}'],
      setupFiles: ['./tests/unit/setup.ts'],
      coverage: {
        provider: 'v8',
        reporter: ['text', 'html'],
        include: ['src/**/*.{ts,tsx}'],
        exclude: ['src/api/generated/**', 'src/routeTree.gen.ts', 'src/main.tsx'],
        thresholds: {
          lines: 80,
          'src/auth/**': { lines: 95 },
          'src/components/schema-form/**': { lines: 95 },
        },
      },
    },
  }),
);
