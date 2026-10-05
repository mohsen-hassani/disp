import { deleteCourse, expect, test, uniqueMarker } from './fixtures';

// M20 §23: the golden path this e2e run can exercise without a real LLM
// key — create a course, add a source, navigate its screens, add a note.
// Indexing/path-generation/quiz/exercise/chat replies all need a real
// model call and are deliberately out of scope here, same as the milestone
// plan's own "live-model verification is deferred" note.
test.describe('learning', () => {
  test('create a course, add a source, and see it on the course detail page', async ({
    authedPage,
    context,
    accessToken,
  }) => {
    const title = uniqueMarker('e2e-course');
    let courseId: string | undefined;

    try {
      await authedPage.goto('/learning');
      await authedPage.getByRole('button', { name: /new course/i }).click();
      await authedPage.getByLabel('Title').fill(title);
      await authedPage.getByRole('button', { name: /^create course$/i }).click();

      await expect(authedPage.getByRole('heading', { name: title, exact: true })).toBeVisible();
      courseId = authedPage.url().split('/learning/')[1];
      expect(courseId).toBeTruthy();

      await authedPage.getByRole('button', { name: /^add source$/i }).click();
      await authedPage.getByLabel('Title').fill('Chapter 1');
      await authedPage.getByLabel('Content').fill('# Heading\n\nSome source content.');
      await authedPage.getByRole('button', { name: /^add source$/i }).click();

      await expect(authedPage.getByText('Chapter 1')).toBeVisible();
    } finally {
      if (courseId) {
        await deleteCourse(context, accessToken, courseId);
      }
    }
  });

  test('adds and deletes a course note', async ({ authedPage, context, accessToken }) => {
    const title = uniqueMarker('e2e-course-notes');
    let courseId: string | undefined;

    try {
      await authedPage.goto('/learning');
      await authedPage.getByRole('button', { name: /new course/i }).click();
      await authedPage.getByLabel('Title').fill(title);
      await authedPage.getByRole('button', { name: /^create course$/i }).click();
      await expect(authedPage.getByRole('heading', { name: title, exact: true })).toBeVisible();
      courseId = authedPage.url().split('/learning/')[1];

      await authedPage.getByRole('link', { name: /notes/i }).click();
      await expect(authedPage.getByRole('heading', { name: 'Notes', exact: true })).toBeVisible();

      const body = uniqueMarker('e2e-note-body');
      await authedPage.getByRole('button', { name: /add note/i }).click();
      await authedPage.getByLabel('Note').fill(body);
      await authedPage.getByRole('button', { name: /^add note$/i }).click();
      await expect(authedPage.getByText(body)).toBeVisible();

      await authedPage.getByRole('button', { name: /^delete$/i }).click();
      await expect(authedPage.getByText(body)).toHaveCount(0);
    } finally {
      if (courseId) {
        await deleteCourse(context, accessToken, courseId);
      }
    }
  });
});
