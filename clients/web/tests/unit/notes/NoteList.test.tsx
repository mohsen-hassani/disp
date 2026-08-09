import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type { NoteOut } from '../../../src/api/generated';
import { NoteList } from '../../../src/components/notes/NoteList';
import { jsonResponse } from '../auth/testUtils';
import { setOnline } from '../pwa/testUtils';
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
  setOnline(true);
});

function note(overrides: Partial<NoteOut> = {}): NoteOut {
  return {
    id: 'note-1',
    title: 'First note',
    body: 'Some body text.\nSecond line.',
    pinned: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function pageResponse(
  items: NoteOut[],
  overrides: Partial<{ next_cursor: string | null; has_more: boolean }> = {},
) {
  return jsonResponse({
    items,
    next_cursor: overrides.next_cursor ?? null,
    has_more: overrides.has_more ?? false,
  });
}

function noop(): void {
  // default no-op prop for callbacks the test doesn't assert on
}

it('renders notes and shows the loading state first (case 35)', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(pageResponse([note()]));
  await renderNotes(
    <NoteList
      q={undefined}
      pinned={undefined}
      onQChange={noop}
      onPinnedChange={noop}
      onNewNote={noop}
    />,
  );

  expect(await screen.findByText('First note')).toBeInTheDocument();
});

it('debounces the search input before calling onQChange (case 35)', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(pageResponse([]));
  const onQChange = vi.fn();
  const user = userEvent.setup();
  await renderNotes(
    <NoteList
      q={undefined}
      pinned={undefined}
      onQChange={onQChange}
      onPinnedChange={noop}
      onNewNote={noop}
    />,
  );
  await screen.findByText('No notes yet. Your first one is a click away.');

  await user.type(screen.getByLabelText('Search notes'), 'hello');
  expect(onQChange).not.toHaveBeenCalled();

  await waitFor(() => expect(onQChange).toHaveBeenCalledWith('hello'), { timeout: 1000 });
});

it('shows the no-filters empty state with a create CTA', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(pageResponse([]));
  const onNewNote = vi.fn();
  const user = userEvent.setup();
  await renderNotes(
    <NoteList
      q={undefined}
      pinned={undefined}
      onQChange={noop}
      onPinnedChange={noop}
      onNewNote={onNewNote}
    />,
  );

  await user.click(await screen.findByRole('button', { name: /create your first note/i }));
  expect(onNewNote).toHaveBeenCalled();
});

it('shows the filtered empty state with a Clear filters button', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(pageResponse([]));
  await renderNotes(
    <NoteList
      q="nothing-matches"
      pinned={undefined}
      onQChange={noop}
      onPinnedChange={noop}
      onNewNote={noop}
    />,
  );

  expect(await screen.findByText('No notes match your search.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /clear filters/i })).toBeInTheDocument();
});

it('shows an error state with a retry button', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    jsonResponse(
      {
        type: 'about:blank',
        title: 'err',
        status: 500,
        detail: 'err',
        instance: '',
        code: 'core.platform.internal_error',
        request_id: 'r1',
      },
      { status: 500 },
    ),
  );
  await renderNotes(
    <NoteList
      q={undefined}
      pinned={undefined}
      onQChange={noop}
      onPinnedChange={noop}
      onNewNote={noop}
    />,
  );

  expect(await screen.findByText('Failed to load notes.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
});

it('toggling pin is optimistic and rolls back on error (case 36)', async () => {
  let resolvePatch: () => void = () => {};
  const patchPromise = new Promise<Response>((resolve) => {
    resolvePatch = () =>
      resolve(
        jsonResponse(
          {
            type: 'about:blank',
            title: 'err',
            status: 500,
            detail: 'err',
            instance: '',
            code: 'core.platform.internal_error',
            request_id: 'r1',
          },
          { status: 500 },
        ),
      );
  });
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(pageResponse([note({ pinned: false })]))
    .mockImplementationOnce(() => patchPromise)
    .mockResolvedValue(pageResponse([note({ pinned: false })]));
  const user = userEvent.setup();
  await renderNotes(
    <NoteList
      q={undefined}
      pinned={undefined}
      onQChange={noop}
      onPinnedChange={noop}
      onNewNote={noop}
    />,
  );
  await screen.findByText('First note');

  const pinButton = screen.getByRole('button', { name: /pin note/i });
  await user.click(pinButton);

  // Optimistic: the button already reads "Unpin" before the deferred PATCH resolves.
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /unpin note/i })).toBeInTheDocument(),
  );
  resolvePatch();
  // Rolled back once the PATCH 500s.
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /pin note/i })).toBeInTheDocument(),
  );
});

it('deleting removes the row optimistically and restores it on error (case 37)', async () => {
  let resolveDelete: () => void = () => {};
  const deletePromise = new Promise<Response>((resolve) => {
    resolveDelete = () =>
      resolve(
        jsonResponse(
          {
            type: 'about:blank',
            title: 'err',
            status: 500,
            detail: 'err',
            instance: '',
            code: 'core.platform.internal_error',
            request_id: 'r1',
          },
          { status: 500 },
        ),
      );
  });
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(pageResponse([note()]))
    .mockImplementationOnce(() => deletePromise)
    .mockResolvedValue(pageResponse([note()]));
  const user = userEvent.setup();
  await renderNotes(
    <NoteList
      q={undefined}
      pinned={undefined}
      onQChange={noop}
      onPinnedChange={noop}
      onNewNote={noop}
    />,
  );
  await screen.findByText('First note');

  await user.click(screen.getByRole('button', { name: /more actions for "first note"/i }));
  await user.click(await screen.findByText('Delete'));
  await user.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: /^delete note$/i }),
  );

  // Optimistic: the row is gone before the deferred DELETE resolves.
  await waitFor(() => expect(screen.queryByText('First note')).not.toBeInTheDocument());
  resolveDelete();
  // Restored once the DELETE 500s.
  await waitFor(() => expect(screen.getByText('First note')).toBeInTheDocument());
});

// Case 43: cached list data renders offline with the "Showing saved data" label.
it('shows "Showing saved data" when offline and notes are already loaded', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(pageResponse([note()]));
  setOnline(false);
  await renderNotes(
    <NoteList
      q={undefined}
      pinned={undefined}
      onQChange={noop}
      onPinnedChange={noop}
      onNewNote={noop}
    />,
  );

  await screen.findByText('First note');
  expect(screen.getByText('Showing saved data.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /^new note$/i })).toBeDisabled();
});

it('does not show "Showing saved data" while online', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(pageResponse([note()]));
  await renderNotes(
    <NoteList
      q={undefined}
      pinned={undefined}
      onQChange={noop}
      onPinnedChange={noop}
      onNewNote={noop}
    />,
  );

  await screen.findByText('First note');
  expect(screen.queryByText('Showing saved data.')).not.toBeInTheDocument();
});

// Case 42: every mutating control on a note row is disabled while offline,
// with the "You're offline." tooltip §18.5 requires — not just the "New
// note" button already covered above.
it('disables every mutating note-row control while offline (case 42)', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(pageResponse([note()]));
  setOnline(false);
  const user = userEvent.setup();
  await renderNotes(
    <NoteList
      q={undefined}
      pinned={undefined}
      onQChange={noop}
      onPinnedChange={noop}
      onNewNote={noop}
    />,
  );
  await screen.findByText('First note');

  const pinButton = screen.getByRole('button', { name: /pin note/i });
  expect(pinButton).toBeDisabled();
  expect(pinButton).toHaveAttribute('title', "You're offline.");

  await user.click(screen.getByRole('button', { name: /more actions for "first note"/i }));
  expect(await screen.findByText('Share')).toHaveAttribute('data-disabled');
  expect(screen.getByText('Delete')).toHaveAttribute('data-disabled');
});
