import { createNote, deleteNote, expect, test, uniqueMarker } from './fixtures';

test.describe('pwa', () => {
  // Case 45 (real-browser half): the built app actually registers a service
  // worker in production preview mode — jsdom-based unit tests can only
  // assert the *config* passed to Workbox, not that registration succeeds.
  test('registers a service worker', async ({ authedPage }) => {
    await authedPage.waitForFunction(
      () => navigator.serviceWorker.getRegistration().then((r) => Boolean(r)),
      { timeout: 15_000 },
    );
  });

  // Case 42: the offline banner appears/disappears with real browser
  // online/offline state, and mutating controls disable with it.
  test('the offline banner appears when offline and mutating controls disable', async ({
    authedPage,
    context,
  }) => {
    await authedPage.goto('/notes');
    // Fully settled first — the page's own JS chunks are still loading
    // right after `goto`, and going offline mid-load breaks navigation
    // itself, not just the thing this test means to exercise.
    await authedPage.getByRole('heading', { name: 'Notes', exact: true }).waitFor();
    await expect(authedPage.getByText(/you're offline/i)).toHaveCount(0);

    await context.setOffline(true);
    await expect(authedPage.getByText(/you're offline/i)).toBeVisible();
    await expect(authedPage.getByRole('button', { name: 'New note' })).toBeDisabled();

    await context.setOffline(false);
    await expect(authedPage.getByText(/you're offline/i)).not.toBeVisible({ timeout: 10_000 });
  });

  // Case 43: already-loaded list data keeps rendering once the connection
  // drops, labelled "Showing saved data" — served from the in-memory
  // TanStack Query cache the earlier online fetch populated. Deliberately
  // does *not* reload while offline: the access token is memory-only by
  // design (§12, no persisted credential), so a reload has no session to
  // recover regardless of what the service worker cached — bootstrap
  // correctly treats that as signed-out, per §8.3's "MUST NOT [degrade]
  // when the server actively rejected the refresh" boundary not applying
  // here, but there being nothing to *resume into* either. This test
  // exercises the supported case: the SPA stays mounted through the
  // online→offline transition.
  test('list data already loaded keeps rendering, labelled saved, once offline', async ({
    authedPage,
    context,
    accessToken,
  }) => {
    const marker = uniqueMarker('pwa-cache');
    const note = await createNote(context, accessToken, { body: marker });

    try {
      await authedPage.goto('/notes');
      await expect(authedPage.getByText(marker).first()).toBeVisible();

      await context.setOffline(true);
      await expect(authedPage.getByText('Showing saved data.')).toBeVisible({ timeout: 10_000 });
      await expect(authedPage.getByText(marker).first()).toBeVisible();
    } finally {
      await context.setOffline(false);
      await deleteNote(context, accessToken, note.id);
    }
  });
});
