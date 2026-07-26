import { defineConfig, devices } from '@playwright/test';

// WEB-SPEC §23.4. `tests/e2e/{auth,dashboard,notes,settings,pwa}.spec.ts`
// run against a real backend: bring up `docker-compose.e2e.yml` first
// (`POSTGRES_PASSWORD=<anything> docker compose -f ../../docker-compose.yml
// -f ../../docker-compose.e2e.yml up -d --build`, from the repo root; see
// that file's own header for why), then `pnpm build` once so `pnpm preview`
// (this config's `webServer`) has a `dist/` to serve — its `preview.proxy`
// (vite.config.ts) is what makes `/api`/`/health`/`/openapi.json` reach that
// backend same-origin (§2.1), standing in for the Traefik routing §24.4
// describes until M12's `web` container exists.

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'pnpm preview',
    url: 'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
  },
});
