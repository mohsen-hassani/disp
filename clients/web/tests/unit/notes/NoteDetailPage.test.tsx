import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type { NoteOut } from '../../../src/api/generated';
import { NoteDetailPage } from '../../../src/routes/-note-detail';
import { jsonResponse } from '../auth/testUtils';
import { renderNotes } from './testUtils';

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
    title: 'Test note',
    body: 'Original body.',
    pinned: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

it('renders the body as inert plain text — script and Markdown are never rendered (case 39)', async () => {
  const bodyText = '<script>alert(1)</script> and **bold** text';
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(jsonResponse(note({ body: bodyText })));
  await renderNotes(<NoteDetailPage noteId="note-1" />);

  expect(await screen.findByText(bodyText)).toBeInTheDocument();
  expect(document.querySelector('script')).toBeNull();
  expect(document.querySelector('strong')).toBeNull();
});

it('inline edit saves the body via PATCH and returns to the display view', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(jsonResponse(note()))
    .mockResolvedValueOnce(jsonResponse(note({ body: 'Updated body.' })));
  const user = userEvent.setup();
  await renderNotes(<NoteDetailPage noteId="note-1" />);
  await screen.findByText('Original body.');

  await user.click(screen.getByRole('button', { name: /^edit$/i }));
  const textarea = screen.getByLabelText(/^body$/i);
  await user.clear(textarea);
  await user.type(textarea, 'Updated body.');
  await user.keyboard('{Control>}{Enter}{/Control}');

  await waitFor(() => expect(screen.getByText('Updated body.')).toBeInTheDocument());
  const [, patchCall] = fetchSpy.mock.calls;
  const patchRequest = patchCall[0] as Request;
  expect(patchRequest.method).toBe('PATCH');
});

it('toggling pin sends the flipped value', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(jsonResponse(note({ pinned: false })))
    .mockResolvedValueOnce(jsonResponse(note({ pinned: true })))
    .mockResolvedValue(jsonResponse(note({ pinned: true })));
  const user = userEvent.setup();
  await renderNotes(<NoteDetailPage noteId="note-1" />);
  await screen.findByText('Test note');

  await user.click(screen.getByRole('button', { name: /pin note/i }));

  function findPatchCall(): Request | undefined {
    return fetchSpy.mock.calls.find(
      (call: unknown[]) => (call[0] as Request).method === 'PATCH',
    )?.[0] as Request | undefined;
  }

  await waitFor(() => expect(findPatchCall()).toBeDefined());
  const patchRequest = findPatchCall() as Request;
  const body = await patchRequest.clone().json();
  expect(body).toEqual({ pinned: true });
});

it('deleting confirms, then navigates back to the list', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(jsonResponse(note()))
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  const user = userEvent.setup();
  const { router } = await renderNotes(<NoteDetailPage noteId="note-1" />);
  await screen.findByText('Test note');

  await user.click(screen.getByRole('button', { name: /more actions/i }));
  await user.click(await screen.findByText('Delete'));
  await user.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: /^delete note$/i }),
  );

  await waitFor(() => expect(router.state.location.pathname).toBe('/notes'));
});
