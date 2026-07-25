import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { setAuthState } from '../../../src/auth/authState';
import { isAdmin, isAuthenticated, RequireAdmin, RequireAuth } from '../../../src/auth/guards';
import { setNavigate } from '../../../src/lib/navigate';
import { TEST_USER } from './testUtils';

let navigateSpy: ReturnType<typeof vi.fn<(path: string) => void>>;

beforeEach(() => {
  navigateSpy = vi.fn<(path: string) => void>();
  setNavigate(navigateSpy);
  window.history.replaceState(null, '', '/notes');
});

afterEach(() => {
  window.history.replaceState(null, '', '/');
});

it('isAuthenticated/isAdmin narrow correctly on each state', () => {
  expect(isAuthenticated({ status: 'anonymous' })).toBe(false);
  expect(isAuthenticated({ status: 'authenticated', user: TEST_USER })).toBe(true);
  expect(isAdmin({ status: 'authenticated', user: TEST_USER })).toBe(false);
  expect(isAdmin({ status: 'authenticated', user: { ...TEST_USER, is_admin: true } })).toBe(true);
  expect(isAdmin({ status: 'anonymous' })).toBe(false);
});

it('RequireAuth renders children when authenticated', () => {
  setAuthState({ status: 'authenticated', user: TEST_USER });

  render(
    <RequireAuth>
      <div>secret content</div>
    </RequireAuth>,
  );

  expect(screen.getByText('secret content')).toBeInTheDocument();
  expect(navigateSpy).not.toHaveBeenCalled();
});

it('RequireAuth redirects to /login?next=<path> when anonymous', async () => {
  setAuthState({ status: 'anonymous' });

  render(
    <RequireAuth>
      <div>secret content</div>
    </RequireAuth>,
  );

  expect(screen.queryByText('secret content')).not.toBeInTheDocument();
  await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith('/login?next=%2Fnotes'));
});

it('RequireAdmin renders a 403 screen for a non-admin, not a redirect', () => {
  setAuthState({ status: 'authenticated', user: TEST_USER }); // is_admin: false

  render(
    <RequireAdmin>
      <div>admin-only content</div>
    </RequireAdmin>,
  );

  expect(screen.queryByText('admin-only content')).not.toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent(/forbidden/i);
  expect(navigateSpy).not.toHaveBeenCalled();
});

it('RequireAdmin renders children for an admin', () => {
  setAuthState({ status: 'authenticated', user: { ...TEST_USER, is_admin: true } });

  render(
    <RequireAdmin>
      <div>admin-only content</div>
    </RequireAdmin>,
  );

  expect(screen.getByText('admin-only content')).toBeInTheDocument();
});
