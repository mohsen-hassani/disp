import { QueryClient } from '@tanstack/react-query';
import { isNotFound } from '@tanstack/react-router';
import { afterAll, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { Route } from '../../../src/routes/_app.notes.$noteId';
import { problemResponse } from '../auth/testUtils';

beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
});

type LoaderArgs = { params: { noteId: string }; context: { queryClient: QueryClient } };

// §16.2's loader-level half of case 40: a `404 notes.not_found` becomes a
// router `notFound()`, which is what makes `notFoundComponent` render
// instead of the component ever mounting against a note that doesn't exist.
it('turns a 404 notes.not_found into a router notFound()', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(problemResponse(404, 'modules.notes.not_found'));
  const queryClient = new QueryClient();
  const loader = Route.options.loader as (args: LoaderArgs) => Promise<void>;

  let thrown: unknown;
  try {
    await loader({ params: { noteId: 'missing' }, context: { queryClient } });
  } catch (error) {
    thrown = error;
  }

  expect(isNotFound(thrown)).toBe(true);
});

it('re-throws a non-404 error rather than treating it as not-found', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(problemResponse(500, 'core.platform.internal_error'));
  const queryClient = new QueryClient();
  const loader = Route.options.loader as (args: LoaderArgs) => Promise<void>;

  let thrown: unknown;
  try {
    await loader({ params: { noteId: 'note-1' }, context: { queryClient } });
  } catch (error) {
    thrown = error;
  }

  expect(isNotFound(thrown)).toBe(false);
});
