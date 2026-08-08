import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  expect,
  expectNoSeriousA11yViolations,
  setTheme,
  test,
  THEMES,
} from './fixtures';

test.describe('auth', () => {
  // Case 2: an anonymous visit to a guarded route redirects to /login?next=…
  test('a guarded route redirects an anonymous visitor to /login with next', async ({ page }) => {
    await page.goto('/notes');
    await expect(page).toHaveURL(/\/login\?next=/);
    expect(decodeURIComponent(page.url())).toContain('next=/notes');
  });

  // Case 4/1: login success stores the session and lands on an authenticated
  // screen — bootstrap on the next load never shows the login form again.
  test('logging in reaches the dashboard, and a reload stays authenticated', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill(ADMIN_EMAIL);
    await page.getByLabel('Password').fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page).toHaveURL('/');
    await expect(page.getByRole('heading', { name: 'DISP' })).toBeVisible();

    await page.reload();
    await expect(page.getByRole('heading', { name: 'DISP' })).toBeVisible();
    await expect(page.getByLabel('Email')).toHaveCount(0);
  });

  // Case 6: one generic error for both invalid-credentials scenarios.
  test('an invalid password shows one generic error, not a field-specific one', async ({
    page,
  }) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill(ADMIN_EMAIL);
    await page.getByLabel('Password').fill('definitely-the-wrong-password');
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page.getByRole('alert')).toHaveText(/don't match/i);
    await expect(page).toHaveURL(/\/login/);
  });

  // §9: /login is anonymous-only — an authenticated visitor is bounced to /.
  test('an already-authenticated visitor hitting /login is bounced to /', async ({
    authedPage,
  }) => {
    await authedPage.goto('/login');
    await expect(authedPage).toHaveURL('/');
  });

  test('signing out returns to a guarded /login, and back-navigating stays signed out', async ({
    authedPage,
  }) => {
    await authedPage.getByRole('button', { name: new RegExp('E2E Admin') }).click();
    await authedPage.getByRole('menuitem', { name: 'Sign out' }).click();

    await expect(authedPage).toHaveURL(/\/login/);
    await expect(authedPage.getByLabel('Email')).toBeVisible();

    await authedPage.goto('/notes');
    await expect(authedPage).toHaveURL(/\/login\?next=/);
  });

  // Case 47: axe scan of the login screen, one of the five key screens.
  for (const theme of THEMES) {
    test(`login screen has no serious/critical accessibility violations (${theme})`, async ({
      page,
    }) => {
      await setTheme(page, theme);
      await page.goto('/login');
      await expectNoSeriousA11yViolations(page);
    });
  }
});
