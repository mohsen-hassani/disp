import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { ShareDialog } from '../../../src/components/notes/ShareDialog';
import { problemResponse } from '../auth/testUtils';
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

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>, email: string) {
  await user.type(screen.getByLabelText(/^email$/i), email);
  await user.click(screen.getByRole('button', { name: /^share$/i }));
}

it('404 notes.user_not_found maps to the email field (case 41)', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(problemResponse(404, 'modules.notes.user_not_found'));
  const user = userEvent.setup();
  await renderNotes(
    <ShareDialog noteId="note-1" noteHeading="My note" open onOpenChange={() => {}} />,
  );

  await fillAndSubmit(user, 'nobody@example.com');

  await waitFor(() => expect(screen.getByText(/no user with that email/i)).toBeInTheDocument());
});

it('400 notes.cannot_share_with_self maps to the email field', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    problemResponse(400, 'modules.notes.cannot_share_with_self', {
      detail: 'You cannot share with yourself.',
    }),
  );
  const user = userEvent.setup();
  await renderNotes(
    <ShareDialog noteId="note-1" noteHeading="My note" open onOpenChange={() => {}} />,
  );

  await fillAndSubmit(user, 'me@example.com');

  await waitFor(() =>
    expect(screen.getByText('You cannot share with yourself.')).toBeInTheDocument(),
  );
});

it('403 closes the dialog and shows a toast', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(problemResponse(403, 'core.acl.forbidden'));
  const onOpenChange = vi.fn();
  const user = userEvent.setup();
  await renderNotes(
    <ShareDialog noteId="note-1" noteHeading="My note" open onOpenChange={onOpenChange} />,
  );

  await fillAndSubmit(user, 'someone@example.com');

  await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  expect(await screen.findByText(/only the owner can share/i)).toBeInTheDocument();
});

it('a successful share closes the dialog and shows a toast', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  const onOpenChange = vi.fn();
  const user = userEvent.setup();
  await renderNotes(
    <ShareDialog noteId="note-1" noteHeading="My note" open onOpenChange={onOpenChange} />,
  );

  await fillAndSubmit(user, 'friend@example.com');

  await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  expect(await screen.findByText(/shared with friend@example.com/i)).toBeInTheDocument();
});
