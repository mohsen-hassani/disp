import {
  expect,
  expectNoSeriousA11yViolations,
  setTheme,
  test,
  THEMES,
  uniqueMarker,
} from './fixtures';

test.describe('settings', () => {
  // The core-registered notifier panel (§14.1's synthetic "core" domain
  // module — CLAUDE.md) renders `urls`/`routing` (free-form maps, outside
  // Appendix B's exhaustive shape) as the disabled fallback, and a no-op
  // save still round-trips against the real PUT endpoint.
  test('the core notifier settings panel renders and a no-op save succeeds', async ({
    authedPage,
  }) => {
    await authedPage.goto('/settings/core');
    await expect(authedPage.getByRole('heading', { name: 'Notifications' })).toBeVisible();
    await expect(authedPage.getByLabel('Urls')).toBeDisabled();
    await expect(authedPage.getByLabel('Routing')).toBeDisabled();

    await authedPage.getByRole('button', { name: /^save$/i }).click();
    // exact: true — Radix Toast's hidden live-region announcer combines the
    // toast's own text with the panel title into "Notification Settings
    // saved.", a second element that would otherwise also match a plain
    // substring search for "Settings saved.".
    await expect(authedPage.getByText('Settings saved.', { exact: true })).toBeVisible();
  });

  test('creating and revoking an API token round-trips against the real backend', async ({
    authedPage,
  }) => {
    const name = uniqueMarker('e2e-token');
    await authedPage.goto('/settings/tokens');

    await authedPage.getByRole('button', { name: 'Create token' }).click();
    await authedPage.getByLabel('Name').fill(name);
    await authedPage.getByRole('dialog').getByRole('button', { name: 'Create token' }).click();

    await expect(authedPage.getByText(`"${name}" created`)).toBeVisible();
    await expect(authedPage.getByText(/copy this token now/i)).toBeVisible();
    await authedPage.getByRole('button', { name: "I've saved it" }).click();

    const row = authedPage.locator('tr', { hasText: name });
    await expect(row).toBeVisible({ timeout: 10_000 });
    await row.getByRole('button', { name: 'Revoke' }).click();
    await authedPage
      .getByRole('dialog')
      .getByRole('button', { name: /^revoke token$/i })
      .click();

    await expect(authedPage.locator('tr', { hasText: name })).toHaveCount(0);
  });

  // Case 47: axe scan of the account settings screen, one of the five key screens.
  for (const theme of THEMES) {
    test(`account settings screen has no serious/critical accessibility violations (${theme})`, async ({
      authedPage,
    }) => {
      await setTheme(authedPage, theme);
      await authedPage.goto('/settings/account');
      await expect(authedPage.getByRole('heading', { name: /change password/i })).toBeVisible();
      await expectNoSeriousA11yViolations(authedPage);
    });
  }
});
