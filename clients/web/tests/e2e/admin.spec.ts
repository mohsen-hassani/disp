import { expect, expectNoSeriousA11yViolations, setTheme, test, THEMES } from './fixtures';

test.describe('admin', () => {
  // Case 47: axe scan of the invitations screen, the fifth of the five key
  // screens (login, dashboard, notes list, account settings, this one) —
  // picked specifically because it had zero e2e coverage of any kind before
  // this test existed, and is structurally distinct from the other four
  // (a table + create-invite dialog, admin-role-gated).
  for (const theme of THEMES) {
    test(`invitations screen has no serious/critical accessibility violations (${theme})`, async ({
      authedPage,
    }) => {
      await setTheme(authedPage, theme);
      await authedPage.goto('/admin/invites');
      // The top bar's page-title <h1> ("Invitations · DISP") and the page's
      // own <h1> ("Invitations") both match a non-exact search — same
      // disambiguation notes.spec.ts already needs for the same reason.
      await expect(
        authedPage.getByRole('heading', { name: 'Invitations', exact: true }),
      ).toBeVisible();
      await expectNoSeriousA11yViolations(authedPage);
    });
  }
});
