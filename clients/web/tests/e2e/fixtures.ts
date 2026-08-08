import AxeBuilder from '@axe-core/playwright';
import { expect, test as base, type BrowserContext, type Page } from '@playwright/test';

// §23.4: the one admin `docker-compose.e2e.yml`'s `migrate` service seeds —
// deterministic via DISP_SEED_PASSWORD, so no test needs to scrape a
// generated password out of container logs. Every spec creates and tears
// down its own note/token/invite fixtures against this account via the API;
// nothing else is assumed to pre-exist.
export const ADMIN_EMAIL = 'e2e-admin@example.com';
export const ADMIN_PASSWORD = 'e2e-admin-password';

interface Fixtures {
  /** Logs the admin in via the API (not the login form) so a spec that
   * doesn't specifically test the login screen can skip it — this also
   * leaves the refresh cookie set on `context`, shared with `page`. */
  accessToken: string;
  /** A page already navigated to `/` with a resolved, authenticated session. */
  authedPage: Page;
}

export const test = base.extend<Fixtures>({
  accessToken: async ({ context }, use) => {
    const response = await context.request.post('/api/auth/login', {
      data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    if (!response.ok()) {
      throw new Error(
        `e2e admin login failed (${response.status()}) — is docker-compose.e2e.yml's ` +
          `migrate service seeded? ${await response.text()}`,
      );
    }
    const body = (await response.json()) as { access_token: string };
    await use(body.access_token);
  },

  authedPage: async ({ page, accessToken }, use) => {
    // Declaring `accessToken` as a dependency (even though only its
    // side effect — the login request that sets the refresh cookie on this
    // context — is needed) makes Playwright run that fixture first;
    // bootstrap (§8.3) then exchanges the cookie for a fresh access token
    // on load, so the page is authenticated without ever touching the
    // login form.
    void accessToken;
    await page.goto('/');
    await page.getByRole('link', { name: 'DISP' }).waitFor();
    await use(page);
  },
});

export { expect };

// M12 §25(21): five key screens, scanned in both themes. Direct
// localStorage injection (not page.emulateMedia) exercises the same
// explicit-preference code path real users hit via the theme toggle —
// emulateMedia only drives the 'system' fallback branch in src/lib/theme.ts.
export const THEMES = ['light', 'dark'] as const;

export async function setTheme(page: Page, theme: (typeof THEMES)[number]): Promise<void> {
  // Must run before the test's own page.goto() — addInitScript only affects
  // *subsequent* navigations, and theme-bootstrap.js (M01) reads this key
  // synchronously before first paint.
  await page.addInitScript((value) => {
    window.localStorage.setItem('disp.theme', value);
  }, theme);
}

export async function expectNoSeriousA11yViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
  const serious = results.violations.filter(
    (v) => v.impact === 'serious' || v.impact === 'critical',
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
}

/**
 * `test.info().testId` is a *stable* hash of the test's file/title, not a
 * random value — reusing it as fixture content means a run whose cleanup
 * didn't complete (e.g. hit the outer test timeout mid-`finally`) leaves
 * data that collides with the *next* run's fixtures of the same test,
 * breaking strict-mode locators expecting exactly one match. Content
 * markers need real per-run uniqueness instead.
 */
export function uniqueMarker(label: string): string {
  return `${label}-${Math.random().toString(36).slice(2)}-${Date.now()}`;
}

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

export interface NoteFixture {
  id: string;
  title: string | null;
  body: string;
}

export async function createNote(
  context: BrowserContext,
  accessToken: string,
  body: { title?: string | null; body: string },
): Promise<NoteFixture> {
  const response = await context.request.post('/api/notes', {
    headers: authHeaders(accessToken),
    data: body,
  });
  if (!response.ok()) {
    throw new Error(`createNote fixture failed (${response.status()}): ${await response.text()}`);
  }
  return response.json();
}

export async function deleteNote(
  context: BrowserContext,
  accessToken: string,
  id: string,
): Promise<void> {
  await context.request.delete(`/api/notes/${id}`, { headers: authHeaders(accessToken) });
}
