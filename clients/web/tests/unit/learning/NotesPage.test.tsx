import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type { DispModulesLearningSchemasNoteOut as NoteOut } from '../../../src/api/generated';
import { NotesPage } from '../../../src/components/learning/NotesPage';
import { jsonResponse } from '../auth/testUtils';
import { renderLearning, routedFetch } from './testUtils';

beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
});

let fetchSpy: ReturnType<typeof vi.spyOn>;
afterEach(() => {
  fetchSpy?.mockRestore();
});

function note(overrides: Partial<NoteOut> = {}): NoteOut {
  return {
    id: 'note-1',
    course_id: 'course-1',
    label: '',
    body: 'Remember: ownership is move by default.',
    path_item_id: null,
    topic_id: null,
    source_section_id: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

it('shows the empty state and creates a note', async () => {
  let notes: NoteOut[] = [];
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch(async (method, path, request) => {
      if (method === 'GET' && path === '/api/learning/courses/course-1/notes') {
        return jsonResponse({ items: notes, next_cursor: null, has_more: false });
      }
      if (method === 'POST' && path === '/api/learning/courses/course-1/notes') {
        const body = (await request.clone().json()) as { body: string };
        notes = [note({ body: body.body })];
        return jsonResponse(notes[0], { status: 201 });
      }
      if (method === 'DELETE' && path === '/api/learning/notes/note-1') {
        notes = [];
        return new Response(null, { status: 204 });
      }
      throw new Error(`Unhandled request in test: ${method} ${path}`);
    }),
  );

  const user = userEvent.setup();
  await renderLearning(<NotesPage courseId="course-1" />);

  expect(await screen.findByText(/no notes yet/i)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /add note/i }));
  await user.type(screen.getByLabelText('Note'), 'Remember: ownership is move by default.');
  await user.click(screen.getByRole('button', { name: /^add note$/i }));

  expect(await screen.findByText('Remember: ownership is move by default.')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /^delete$/i }));

  expect(await screen.findByText(/no notes yet/i)).toBeInTheDocument();
});
