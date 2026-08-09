import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { AccountPage } from '../../../src/routes/-account';
import { meResponse, problemResponse } from '../auth/testUtils';
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

async function fillPasswordForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/current password/i), 'old-password-123');
  await user.type(screen.getByLabelText(/^new password/i), 'new-password-456');
  await user.type(screen.getByLabelText(/confirm new password/i), 'new-password-456');
}

it('renders the read-only account info from GET /api/auth/me', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(meResponse());
  renderWithProviders(<AccountPage />);

  expect(await screen.findByText('Test User')).toBeInTheDocument();
  expect(screen.getByText('test@example.com')).toBeInTheDocument();
  expect(screen.getByText('Member')).toBeInTheDocument();
});

it('changing the password successfully resets the form and shows a toast', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(meResponse())
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  const user = userEvent.setup();
  renderWithProviders(<AccountPage />);
  await screen.findByText('Test User');

  await fillPasswordForm(user);
  await user.click(screen.getByRole('button', { name: /change password/i }));

  await waitFor(() =>
    expect(screen.getByText(/signed out of your other sessions/i)).toBeInTheDocument(),
  );
  expect(screen.getByLabelText(/current password/i)).toHaveValue('');
});

it('maps a 401 to the current-password field', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(meResponse())
    .mockResolvedValueOnce(problemResponse(401, 'core.auth.invalid_credentials'));
  const user = userEvent.setup();
  renderWithProviders(<AccountPage />);
  await screen.findByText('Test User');

  await fillPasswordForm(user);
  await user.click(screen.getByRole('button', { name: /change password/i }));

  await waitFor(() =>
    expect(screen.getByText(/doesn't match your current one/i)).toBeInTheDocument(),
  );
});

it('maps a 422 auth.password_policy to the new-password field using the server detail', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(meResponse())
    .mockResolvedValueOnce(
      problemResponse(422, 'core.auth.password_policy', { detail: 'Too common a password.' }),
    );
  const user = userEvent.setup();
  renderWithProviders(<AccountPage />);
  await screen.findByText('Test User');

  await fillPasswordForm(user);
  await user.click(screen.getByRole('button', { name: /change password/i }));

  await waitFor(() => expect(screen.getByText('Too common a password.')).toBeInTheDocument());
});

it('blocks submit client-side when the confirmation does not match', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(meResponse());
  const user = userEvent.setup();
  renderWithProviders(<AccountPage />);
  await screen.findByText('Test User');

  await user.type(screen.getByLabelText(/current password/i), 'old-password-123');
  await user.type(screen.getByLabelText(/^new password/i), 'new-password-456');
  await user.type(screen.getByLabelText(/confirm new password/i), 'something-else');
  await user.click(screen.getByRole('button', { name: /change password/i }));

  await waitFor(() => expect(screen.getByText(/don't match/i)).toBeInTheDocument());
  // Only the /auth/me GET happened — no change-password request was sent.
  expect(fetchSpy).toHaveBeenCalledTimes(1);
});
