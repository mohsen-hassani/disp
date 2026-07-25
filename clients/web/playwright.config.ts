import { defineConfig, devices } from '@playwright/test';

// WEB-SPEC §23.4: real e2e specs (auth/dashboard/notes/settings/pwa) and the
// docker-compose.e2e.yml-backed backend are M11's job. This config exists now
// so the file is present and typechecks per M01's scope; `pnpm preview`
// serves the static build for `test:e2e` to run against once specs exist.
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
