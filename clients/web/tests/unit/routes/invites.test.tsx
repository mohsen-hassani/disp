import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { InvitesPage } from '../../../src/routes/-invites';
import { jsonResponse, problemResponse } from '../auth/testUtils';
import { renderWithProviders } from './testUtils';

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

const EXISTING_INVITE = {
  id: 'invite-1',
  email: 'pending@example.com',
  is_admin: false,
  expires_at: new Date(Date.now() + 86_400_000).toISOString(),
  created_at: new Date().toISOString(),
};

function invitesListResponse(invites: unknown[] = [EXISTING_INVITE]) {
  return jsonResponse(invites);
}

async function openCreateDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /invite someone/i }));
}

it('lists pending invites', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(invitesListResponse());
  renderWithProviders(<InvitesPage />);

  expect(await screen.findByText('pending@example.com')).toBeInTheDocument();
});

it('creating an invite reveals the accept_url once, with the no-email-sent copy', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(invitesListResponse([]))
    .mockResolvedValueOnce(
      jsonResponse(
        {
          id: 'invite-2',
          email: 'new-person@example.com',
          token: 'raw-invite-token',
          accept_url: 'http://localhost/accept-invite?token=raw-invite-token',
          expires_at: new Date(Date.now() + 86_400_000).toISOString(),
        },
        { status: 201 },
      ),
    )
    .mockResolvedValueOnce(
      invitesListResponse([{ ...EXISTING_INVITE, email: 'new-person@example.com' }]),
    );
  const user = userEvent.setup();
  renderWithProviders(<InvitesPage />);
  await screen.findByText('No pending invites.');

  await openCreateDialog(user);
  await user.type(screen.getByLabelText(/^email$/i), 'new-person@example.com');
  await user.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: /create invite/i }),
  );

  await waitFor(() =>
    expect(
      screen.getByText('http://localhost/accept-invite?token=raw-invite-token'),
    ).toBeInTheDocument(),
  );
  expect(screen.getByText(/disp doesn't send email/i)).toBeInTheDocument();

  await user.keyboard('{Escape}');
  expect(
    screen.getByText('http://localhost/accept-invite?token=raw-invite-token'),
  ).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /i've saved it/i }));
  expect(
    screen.queryByText('http://localhost/accept-invite?token=raw-invite-token'),
  ).not.toBeInTheDocument();
});

it('maps 409 auth.user_exists and auth.invite_pending to the email field with distinct copy', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(invitesListResponse([]))
    .mockResolvedValueOnce(problemResponse(409, 'auth.user_exists'));
  const user = userEvent.setup();
  renderWithProviders(<InvitesPage />);
  await screen.findByText('No pending invites.');

  await openCreateDialog(user);
  await user.type(screen.getByLabelText(/^email$/i), 'existing@example.com');
  await user.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: /create invite/i }),
  );

  await waitFor(() => expect(screen.getByText(/already exists/i)).toBeInTheDocument());

  fetchSpy.mockResolvedValueOnce(problemResponse(409, 'auth.invite_pending'));
  await user.clear(screen.getByLabelText(/^email$/i));
  await user.type(screen.getByLabelText(/^email$/i), 'someone@example.com');
  await user.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: /create invite/i }),
  );

  await waitFor(() =>
    expect(screen.getByText(/pending invite already exists/i)).toBeInTheDocument(),
  );
});

it('revoking asks for confirmation naming the specific invite', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(invitesListResponse())
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(invitesListResponse([]));
  const user = userEvent.setup();
  renderWithProviders(<InvitesPage />);
  await screen.findByText('pending@example.com');

  await user.click(screen.getByRole('button', { name: /^revoke$/i }));
  expect(screen.getByText(/revoke invite to "pending@example.com"/i)).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /^revoke invite$/i }));
  await waitFor(() => expect(screen.getByText('No pending invites.')).toBeInTheDocument());
});
