import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { qk } from '../../../src/api/queryKeys';
import {
  CreateNoteDialogProvider,
  useCreateNoteDialog,
} from '../../../src/components/notes/CreateNoteDialogProvider';
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

function OpenButton() {
  const { open } = useCreateNoteDialog();
  return (
    <button type="button" onClick={open}>
      Open create dialog
    </button>
  );
}

function createdNoteResponse() {
  return jsonResponse(
    {
      id: 'new-note',
      title: null,
      body: 'Hello there.',
      pinned: false,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    { status: 201 },
  );
}

it('creating a note invalidates the list and the notes tile (case 38)', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(createdNoteResponse());
  const user = userEvent.setup();
  const { queryClient } = await renderNotes(
    <CreateNoteDialogProvider>
      <OpenButton />
    </CreateNoteDialogProvider>,
  );
  const listKey = qk.notes.list({});
  const tileKey = qk.dashboard.tile('notes.latest');
  queryClient.setQueryData(listKey, { pages: [], pageParams: [] });
  queryClient.setQueryData(tileKey, {});

  await user.click(screen.getByRole('button', { name: /open create dialog/i }));
  await user.type(screen.getByLabelText(/^body/i), 'Hello there.');
  await user.click(screen.getByRole('button', { name: /^create note$/i }));

  await waitFor(() => expect(queryClient.getQueryState(listKey)?.isInvalidated).toBe(true));
  expect(queryClient.getQueryState(tileKey)?.isInvalidated).toBe(true);
});

it('closes the dialog and shows a toast with an Open action on success', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(createdNoteResponse());
  const user = userEvent.setup();
  await renderNotes(
    <CreateNoteDialogProvider>
      <OpenButton />
    </CreateNoteDialogProvider>,
  );

  await user.click(screen.getByRole('button', { name: /open create dialog/i }));
  await user.type(screen.getByLabelText(/^body/i), 'Hello there.');
  await user.click(screen.getByRole('button', { name: /^create note$/i }));

  await waitFor(() => expect(screen.getByText('Note created.')).toBeInTheDocument());
  expect(screen.getByRole('button', { name: /^open$/i })).toBeInTheDocument();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('Cmd/Ctrl+Enter submits the create form', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(createdNoteResponse());
  const user = userEvent.setup();
  await renderNotes(
    <CreateNoteDialogProvider>
      <OpenButton />
    </CreateNoteDialogProvider>,
  );

  await user.click(screen.getByRole('button', { name: /open create dialog/i }));
  await user.type(screen.getByLabelText(/^body/i), 'Hello there.');
  await user.keyboard('{Control>}{Enter}{/Control}');

  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
});
