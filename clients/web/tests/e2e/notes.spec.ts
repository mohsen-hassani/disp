import {
  createNote,
  deleteNote,
  expect,
  expectNoSeriousA11yViolations,
  setTheme,
  test,
  THEMES,
  uniqueMarker,
} from './fixtures';

test.describe('notes', () => {
  // Case 47: axe scan of the notes list, one of the five key screens.
  for (const theme of THEMES) {
    test(`notes list has no serious/critical accessibility violations (${theme})`, async ({
      authedPage,
    }) => {
      await setTheme(authedPage, theme);
      await authedPage.goto('/notes');
      // Both the page's own <h1> and the top bar's page-title <h1> contain
      // "Notes" — `exact` picks out the page's own heading specifically.
      await expect(authedPage.getByRole('heading', { name: 'Notes', exact: true })).toBeVisible();
      await expectNoSeriousA11yViolations(authedPage);
    });
  }

  // Case 35: search is debounced and the term is reflected in the URL.
  test('search filters the list and reflects the term in the URL', async ({
    authedPage,
    context,
    accessToken,
  }) => {
    const unique = uniqueMarker('zzsearchable');
    const other = uniqueMarker('zzunrelated');
    const matching = await createNote(context, accessToken, { body: unique });
    const otherNote = await createNote(context, accessToken, { body: other });

    try {
      await authedPage.goto('/notes');
      await expect(authedPage.getByText(unique).first()).toBeVisible();
      await expect(authedPage.getByText(other).first()).toBeVisible();

      await authedPage.getByRole('searchbox').fill(unique);
      await expect(authedPage).toHaveURL(new RegExp(`q=${unique}`), { timeout: 2000 });
      await expect(authedPage.getByText(other)).toHaveCount(0);
      await expect(authedPage.getByText(unique).first()).toBeVisible();
    } finally {
      await deleteNote(context, accessToken, matching.id);
      await deleteNote(context, accessToken, otherNote.id);
    }
  });

  test('creating a note via the dialog adds it to the list', async ({
    authedPage,
    context,
    accessToken,
  }) => {
    const unique = uniqueMarker('created');
    await authedPage.goto('/notes');

    await authedPage.getByRole('button', { name: 'New note' }).click();
    await authedPage.getByLabel('Body').fill(unique);
    await authedPage.getByRole('dialog').getByRole('button', { name: 'Create note' }).click();

    await expect(authedPage.getByText(unique).first()).toBeVisible();

    const response = await context.request.get('/api/notes', {
      headers: { Authorization: `Bearer ${accessToken}` },
      params: { q: unique },
    });
    const { items } = (await response.json()) as { items: { id: string }[] };
    for (const item of items) {
      await deleteNote(context, accessToken, item.id);
    }
  });

  test('pinning and deleting round-trip against the real backend', async ({
    authedPage,
    context,
    accessToken,
  }) => {
    const unique = uniqueMarker('pin-delete');
    const note = await createNote(context, accessToken, { body: unique });
    let cleaned = false;

    try {
      await authedPage.goto('/notes');
      const row = authedPage.locator('article', { hasText: unique });
      await row.getByRole('button', { name: /pin note/i }).click();
      await expect(row.getByRole('button', { name: /unpin note/i })).toBeVisible();

      await row.getByRole('button', { name: /more actions/i }).click();
      await authedPage.getByRole('menuitem', { name: 'Delete' }).click();
      await authedPage
        .getByRole('dialog')
        .getByRole('button', { name: /^delete note$/i })
        .click();

      await expect(authedPage.getByText(unique)).toHaveCount(0);
      cleaned = true;
    } finally {
      if (!cleaned) {
        await deleteNote(context, accessToken, note.id);
      }
    }
  });

  // Case 39: a note body containing script/Markdown-looking text renders
  // literally, never interpreted — the real XSS-relevant check, run against
  // actual browser rendering rather than jsdom.
  test('a note body with script-like content renders as inert text', async ({
    authedPage,
    context,
    accessToken,
  }) => {
    const marker = uniqueMarker('xss-marker');
    const dangerous = `<script>window.__xss_${marker.replaceAll('-', '_')}__ = true</script> **bold** ${marker}`;
    const note = await createNote(context, accessToken, { body: dangerous });

    try {
      await authedPage.goto(`/notes/${note.id}`);
      await expect(authedPage.getByText(marker)).toBeVisible();
      const ran = await authedPage.evaluate(
        (m) => (window as unknown as Record<string, unknown>)[`__xss_${m}__`],
        marker.replaceAll('-', '_'),
      );
      expect(ran).toBeUndefined();
      // Markdown syntax appears literally — no <strong> was rendered from it.
      await expect(authedPage.locator('strong', { hasText: 'bold' })).toHaveCount(0);
    } finally {
      await deleteNote(context, accessToken, note.id);
    }
  });

  // Case 40 (render half): a 404 shows the not-found screen, not a toast.
  test('visiting a nonexistent note shows the not-found screen', async ({ authedPage }) => {
    await authedPage.goto('/notes/00000000-0000-0000-0000-000000000000');
    await expect(authedPage.getByRole('heading', { name: /not found/i })).toBeVisible();
    // The toast list (always mounted, per ToastProvider) has no items —
    // distinct from __root.tsx's own unrelated aria-live title announcer.
    await expect(
      authedPage.getByRole('region', { name: /notifications/i }).getByRole('listitem'),
    ).toHaveCount(0);
  });

  // Case 49: the delete-confirm dialog traps focus, and Escape restores it
  // to the "more actions" trigger that (indirectly) opened it.
  test('the delete-confirm dialog traps focus and restores it to the trigger on Escape', async ({
    authedPage,
    context,
    accessToken,
  }) => {
    const unique = uniqueMarker('focus-trap');
    const note = await createNote(context, accessToken, { body: unique });

    try {
      await authedPage.goto('/notes');
      const row = authedPage.locator('article', { hasText: unique });
      const moreButton = row.getByRole('button', { name: /more actions/i });
      await moreButton.click();
      await authedPage.getByRole('menuitem', { name: 'Delete' }).click();

      const dialog = authedPage.getByRole('dialog');
      await expect(dialog).toBeVisible();

      // Tabbing forward repeatedly never leaves the dialog.
      for (let i = 0; i < 6; i++) {
        await authedPage.keyboard.press('Tab');
        const withinDialog = await dialog.evaluate(
          (node, active) => node.contains(active),
          await authedPage.evaluateHandle(() => document.activeElement),
        );
        expect(withinDialog).toBeTruthy();
      }

      await authedPage.keyboard.press('Escape');
      await expect(dialog).not.toBeVisible();
      await expect(moreButton).toBeFocused();
    } finally {
      await deleteNote(context, accessToken, note.id);
    }
  });
});
