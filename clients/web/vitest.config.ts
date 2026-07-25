import { defineConfig, mergeConfig } from 'vitest/config';

import viteConfig from './vite.config';

// WEB-SPEC §23.1/§23.2: Vitest + RTL + MSW own the unit/component layer;
// Playwright (playwright.config.ts) owns e2e. Coverage gates (≥80% overall,
// ≥95% on src/auth/ and src/components/schema-form/) are tightened in M11
// once those directories have real code to measure — enforcing a hard
// threshold here today would fail on an empty tree with nothing to test yet.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      include: ['tests/unit/**/*.{test,spec}.{ts,tsx}'],
      coverage: {
        provider: 'v8',
        reporter: ['text', 'html'],
        include: ['src/**/*.{ts,tsx}'],
        exclude: ['src/api/generated/**', 'src/routeTree.gen.ts', 'src/main.tsx'],
      },
    },
  }),
);
