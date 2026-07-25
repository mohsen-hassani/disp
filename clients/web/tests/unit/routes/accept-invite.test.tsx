import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { setAuthState } from '../../../src/auth/authState';
import { getToken } from '../../../src/auth/tokenStore';
import { setNavigate } from '../../../src/lib/navigate';
import { AcceptInvitePage } from '../../../src/routes/accept-invite';
import { loginResponse, problemResponse } from '../auth/testUtils';

beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
});

let fetchSpy: ReturnType<typeof vi.spyOn>;
let navigateSpy: ReturnType<typeof vi.fn<(path: string) => void>>;

beforeEach(() => {
  fetchSpy = vi.spyOn(globalThis, 'fetch');
  navigateSpy = vi.fn<(path: string) => void>();
  setNavigate(navigateSpy);
  setAuthState({ status: 'anonymous' });
});

afterEach(() => {
  fetchSpy.mockRestore();
  window.history.replaceState(null, '', '/accept-invite');
});

it('shows the not-found state immediately when no token is in the URL', () => {
  render(<AcceptInvitePage />);
  expect(screen.getByText(/we couldn't find that invitation/i)).toBeInTheDocument();
  expect(fetchSpy).not.toHaveBeenCalled();
});

it('accepts a valid invite, stores the token, and navigates to /', async () => {
  window.history.replaceState(null, '', '/accept-invite?token=abc123');
  fetchSpy.mockResolvedValueOnce(loginResponse({ access_token: 'invite-token' }));

  render(<AcceptInvitePage />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/display name/i), 'New Person');
  await user.type(screen.getByLabelText(/^password$/i), 'correct horse battery staple');
  await user.type(screen.getByLabelText(/confirm password/i), 'correct horse battery staple');
  await user.click(screen.getByRole('button', { name: /accept invitation/i }));

  await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/'));
  expect(getToken()).toBe('invite-token');

  const call = fetchSpy.mock.calls.find((c: unknown[]) => {
    const req = c[0] as Request;
    return new URL(req.url).pathname === '/api/auth/accept-invite';
  });
  expect(call).toBeDefined();
});

it('shows the expired-invite screen on 410 auth.invite_expired', async () => {
  window.history.replaceState(null, '', '/accept-invite?token=abc123');
  fetchSpy.mockResolvedValueOnce(problemResponse(410, 'auth.invite_expired'));

  render(<AcceptInvitePage />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/display name/i), 'New Person');
  await user.type(screen.getByLabelText(/^password$/i), 'correct horse battery staple');
  await user.type(screen.getByLabelText(/confirm password/i), 'correct horse battery staple');
  await user.click(screen.getByRole('button', { name: /accept invitation/i }));

  expect(await screen.findByText(/this invitation has expired/i)).toBeInTheDocument();
});
