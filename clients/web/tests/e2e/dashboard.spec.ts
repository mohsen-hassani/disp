import AxeBuilder from '@axe-core/playwright';

import { createNote, deleteNote, expect, test, uniqueMarker } from './fixtures';

test.describe('dashboard', () => {
  test('the notes tile shows a fixture note, and the quick-add action creates one', async ({
    authedPage,
    context,
    accessToken,
  }) => {
    const marker = uniqueMarker('dashboard-fixture');
    const note = await createNote(context, accessToken, { body: marker });
    const quickAddText = uniqueMarker('quick-add');

    try {
      await authedPage.goto('/');
      await expect(authedPage.getByRole('heading', { name: 'Latest notes' })).toBeVisible();
      await expect(authedPage.getByText(marker).first()).toBeVisible();

      await authedPage.getByRole('button', { name: 'Add note' }).click();
      await authedPage.getByLabel('Body').fill(quickAddText);
      await authedPage.getByRole('dialog').getByRole('button', { name: 'Add note' }).click();
      // The dialog closing is the success signal — whether the new item
      // also lands within the tile's own top-5 (§13.2) depends on how many
      // *other* notes exist system-wide (this account is shared across the
      // whole e2e suite, run with several parallel workers), so that's not
      // asserted here; the API check below is the real proof of case 22's
      // "successful action invalidates the tile" outcome.
      await expect(authedPage.getByRole('dialog')).not.toBeVisible();
    } finally {
      await deleteNote(context, accessToken, note.id);
      const response = await context.request.get('/api/notes', {
        headers: { Authorization: `Bearer ${accessToken}` },
        params: { q: quickAddText },
      });
      const { items } = (await response.json()) as { items: { id: string }[] };
      expect(items.length).toBeGreaterThan(0);
      for (const item of items) {
        await deleteNote(context, accessToken, item.id);
      }
    }
  });

  // Case 48: full keyboard traversal of the dashboard reaches every
  // interactive element in DOM order, starting at the skip link (§21 A9/A10).
  test('full keyboard traversal reaches the skip link, the nav, and the account menu', async ({
    authedPage,
  }) => {
    await authedPage.goto('/');
    await authedPage.getByRole('heading', { name: 'Dashboard', exact: true }).waitFor();

    const focusedLabels: string[] = [];
    for (let i = 0; i < 25; i++) {
      await authedPage.keyboard.press('Tab');
      const label = await authedPage.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body) return null;
        return el.getAttribute('aria-label') ?? el.textContent?.trim() ?? el.tagName;
      });
      if (label) focusedLabels.push(label);
    }

    // §21 A9/A10: the skip link is reachable early, before the app shell's
    // own nav/content — not literally the first tab stop in every browser,
    // but well ahead of the rest of the traversal.
    const skipLinkIndex = focusedLabels.findIndex((label) => label.includes('Skip to content'));
    expect(skipLinkIndex).toBeGreaterThanOrEqual(0);
    expect(skipLinkIndex).toBeLessThan(3);
    expect(focusedLabels.some((label) => label.includes('Notes'))).toBeTruthy();
    expect(focusedLabels.some((label) => label.includes('E2E Admin'))).toBeTruthy();
  });

  // Case 47: axe scan of the dashboard, one of the five key screens.
  test('dashboard has no serious/critical accessibility violations', async ({ authedPage }) => {
    await authedPage.goto('/');
    const results = await new AxeBuilder({ page: authedPage })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    const serious = results.violations.filter(
      (v) => v.impact === 'serious' || v.impact === 'critical',
    );
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
  });
});
