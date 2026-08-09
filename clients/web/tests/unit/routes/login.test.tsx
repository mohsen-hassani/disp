import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { getAuthState, setAuthState } from '../../../src/auth/authState';
import { getToken } from '../../../src/auth/tokenStore';
import { setNavigate } from '../../../src/lib/navigate';
import { LoginPage, resolveNextPath } from '../../../src/routes/-login';
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
  vi.useRealTimers();
  window.history.replaceState(null, '', '/login');
});

async function fillAndSubmit(email: string, password: string): Promise<void> {
  const user = userEvent.setup();
  const emailField = screen.getByLabelText(/email/i);
  const passwordField = screen.getByLabelText(/^password$/i);
  await user.clear(emailField);
  await user.type(emailField, email);
  await user.clear(passwordField);
  await user.type(passwordField, password);
  await user.click(screen.getByRole('button', { name: /sign in/i }));
}

// Case 5: an absolute-URL `next` is ignored; a pure function, tested directly.
it('resolveNextPath ignores absolute and protocol-relative URLs', () => {
  expect(resolveNextPath('https://evil.example/steal')).toBe('/');
  expect(resolveNextPath('//evil.example/steal')).toBe('/');
  expect(resolveNextPath(null)).toBe('/');
  expect(resolveNextPath('/notes')).toBe('/notes');
});

// Case 4: login success stores the token and navigates to `next`.
it('stores the token and navigates to next on success', async () => {
  window.history.replaceState(null, '', '/login?next=%2Fnotes');
  fetchSpy.mockResolvedValueOnce(loginResponse({ access_token: 'fresh-token' }));

  render(<LoginPage />);
  await fillAndSubmit('user@example.com', 'correct horse battery staple');

  await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/notes'));
  expect(getToken()).toBe('fresh-token');
});

// Case 5 (navigation half): an absolute `next` in the actual URL falls back to `/`.
it('falls back to / when next in the URL is an absolute URL', async () => {
  window.history.replaceState(null, '', '/login?next=https%3A%2F%2Fevil.example');
  fetchSpy.mockResolvedValueOnce(loginResponse());

  render(<LoginPage />);
  await fillAndSubmit('user@example.com', 'correct horse battery staple');

  await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/'));
});

// Case 6: a 401 shows one generic error, identical for both failure modes.
it('shows the same generic error for both invalid-credentials scenarios', async () => {
  fetchSpy.mockResolvedValueOnce(problemResponse(401, 'core.auth.invalid_credentials'));

  render(<LoginPage />);
  await fillAndSubmit('unknown@example.com', 'whatever-password');

  const firstError = await screen.findByRole('alert');
  expect(firstError).toHaveTextContent(/that email and password don't match/i);

  fetchSpy.mockResolvedValueOnce(problemResponse(401, 'core.auth.invalid_credentials'));
  await fillAndSubmit('known@example.com', 'wrong-password');

  const secondError = await screen.findByRole('alert');
  expect(secondError).toHaveTextContent(/that email and password don't match/i);
  expect(secondError.textContent).toBe(firstError.textContent);
});

// Case 3 (UI half): the persistent security banner renders on the login
// screen when bootstrap/refresh already put auth state into `revoked`, and
// dismissing it acknowledges the state back to `anonymous` (§8.6).
it('renders the security banner when revoked, and Dismiss acknowledges it', async () => {
  setAuthState({ status: 'revoked', reason: 'reuse_detected' });

  render(<LoginPage />);

  const banner = screen.getByRole('alert');
  expect(banner).toHaveTextContent(/signed out because your session token was used twice/i);

  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: /dismiss/i }));

  expect(getAuthState()).toEqual({ status: 'anonymous' });
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('does not render the security banner when merely anonymous', () => {
  setAuthState({ status: 'anonymous' });
  render(<LoginPage />);
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

// Case 7: a 429 disables submit for Retry-After seconds with a countdown.
it('disables submit and counts down on a 429', async () => {
  fetchSpy.mockResolvedValueOnce(
    problemResponse(429, 'core.platform.rate_limited', { headers: { 'Retry-After': '5' } }),
  );

  render(<LoginPage />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/email/i), 'user@example.com');
  await user.type(screen.getByLabelText(/^password$/i), 'correct horse battery staple');
  await user.click(screen.getByRole('button', { name: /sign in/i }));

  const button = await screen.findByRole('button', { name: /try again in 5s/i });
  expect(button).toBeDisabled();

  await waitFor(
    () =>
      expect(screen.getByRole('button', { name: /try again in \ds/i })).toHaveTextContent(
        /try again in [1-4]s/i,
      ),
    { timeout: 2000 },
  );

  await waitFor(
    () => expect(screen.getByRole('button', { name: /^sign in$/i })).not.toBeDisabled(),
    { timeout: 6000 },
  );
}, 10000);
