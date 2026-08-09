import { deletePlant, expect, test, uniqueMarker } from './fixtures';

// M14 §7: create → add interval → mark done → verify the reschedule →
// delete, driven end to end through the real UI against the real backend.
// The reschedule assertion is the actual point of the test (M14 §1): a
// 15-day interval last done 20 days ago is overdue by 5 days; completing it
// 2 days ago must schedule the *next* occurrence from that completion date
// (today + 13), not from the original due date (today + 10) — the two
// diverge by exactly the gap between "done" and "due", so no
// client-side-computed date could accidentally satisfy this assertion.
test.describe('plants', () => {
  function localDate(offsetDays: number): string {
    const date = new Date();
    date.setDate(date.getDate() + offsetDays);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  test('create, add an interval, mark it done, verify the reschedule, then delete', async ({
    authedPage,
    context,
    accessToken,
  }) => {
    const name = uniqueMarker('e2e-plant');
    let plantId: string | undefined;

    try {
      await authedPage.goto('/plants/new');
      await authedPage.getByLabel(/^name/i).fill(name);
      await authedPage.getByRole('button', { name: 'Create plant' }).click();

      // `exact: true` — the TopBar's own page-title heading also contains
      // the plant name (as "<name> · DISP"), matching `notes.spec.ts`'s
      // same disambiguation for its list heading.
      await expect(authedPage.getByRole('heading', { name, exact: true })).toBeVisible();
      plantId = authedPage.url().split('/plants/')[1];
      expect(plantId).toBeTruthy();

      // Add a 15-day interval last done 20 days ago — 5 days overdue.
      await authedPage.getByRole('button', { name: 'Add interval' }).click();
      const addDialog = authedPage.getByRole('dialog');
      await addDialog.getByLabel('Name').fill('Water');
      const daysField = addDialog.getByLabel(/repeat every/i);
      await daysField.fill('15');
      await addDialog.getByLabel(/last done on/i).fill(localDate(-20));
      await addDialog.getByRole('button', { name: 'Add interval' }).click();

      await expect(authedPage.getByText('5 days overdue')).toBeVisible();

      // Mark done, back-dated 2 days — reschedules from the completion
      // date (today - 2 + 15 = today + 13), not the original due date.
      await authedPage.getByRole('button', { name: 'Mark done' }).click();
      const completeDialog = authedPage.getByRole('dialog');
      await completeDialog.getByLabel(/completed on/i).fill(localDate(-2));
      await completeDialog.getByRole('button', { name: 'Mark done' }).click();

      const expectedNextDue = new Date(localDate(-2));
      expectedNextDue.setDate(expectedNextDue.getDate() + 15);
      const expectedLabel = expectedNextDue.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });

      await expect(authedPage.getByText('5 days overdue')).toHaveCount(0);
      await expect(authedPage.getByText(`Due ${expectedLabel}`)).toBeVisible();

      // Delete via the UI — the point of the test is that this path works,
      // not just the API fallback in the `finally` block below.
      // `exact: true` — Playwright's default string match is substring, and
      // the interval row's own "More actions for "Water"" trigger would
      // otherwise also match.
      await authedPage.getByRole('button', { name: 'More actions', exact: true }).click();
      await authedPage.getByRole('menuitem', { name: 'Delete' }).click();
      await authedPage
        .getByRole('dialog')
        .getByRole('button', { name: /^delete plant$/i })
        .click();

      await expect(authedPage).toHaveURL(/\/plants$/);
      await expect(authedPage.getByText(name)).toHaveCount(0);
      plantId = undefined;
    } finally {
      if (plantId) {
        await deletePlant(context, accessToken, plantId);
      }
    }
  });
});
