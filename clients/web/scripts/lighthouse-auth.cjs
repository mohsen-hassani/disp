// LHCI's puppeteerScript hook — receives an already-connected Puppeteer
// `page` before each collection run navigates to its target URL (LHCI owns
// the browser lifecycle; this script never launches its own). Logs in via
// the API (matching the Playwright e2e fixtures' approach in
// tests/e2e/fixtures.ts, duplicated rather than imported since that file is
// TypeScript and this runs as plain CommonJS under LHCI) so the subsequent
// navigation lands authenticated — §2.4's access token lives in memory
// only, but the login call also sets the httpOnly refresh cookie, which the
// app's bootstrap (§8.3) exchanges for a fresh access token on page load.
//
// Requires the e2e backend stack (docker-compose.e2e.yml) already running
// at the same origin LHCI collects against — not wired into CI yet (see
// clients/web/lighthouserc.cjs's header comment).
const ADMIN_EMAIL = 'e2e-admin@example.com';
const ADMIN_PASSWORD = 'e2e-admin-password';

module.exports = async (page, context) => {
  if (!context.url.includes('/login')) {
    await page.goto(new URL('/login', context.url).toString());
    await page.evaluate(
      async (email, password) => {
        await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
      },
      ADMIN_EMAIL,
      ADMIN_PASSWORD,
    );
  }
};
