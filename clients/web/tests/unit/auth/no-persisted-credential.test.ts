import { afterAll, beforeAll, beforeEach, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { login } from '../../../src/auth/AuthProvider';
import { setAuthState } from '../../../src/auth/authState';
import { getToken } from '../../../src/auth/tokenStore';
import { loginResponse } from './testUtils';

beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
});

beforeEach(() => {
  setAuthState({ status: 'anonymous' });
  localStorage.clear();
  sessionStorage.clear();
});

// Case 12: after a full login flow, no credential (access token or
// password) reaches localStorage, sessionStorage, or any Cache Storage
// entry — the token lives only in tokenStore's module-scoped variable.
it('does not persist the access token or password anywhere after login', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    loginResponse({ access_token: 'super-secret-token' }),
  );

  const PASSWORD = 'correct horse battery staple';
  await login('user@example.com', PASSWORD);

  expect(getToken()).toBe('super-secret-token');

  const allLocalStorageValues = Object.keys(localStorage).map((key) => localStorage.getItem(key));
  const allSessionStorageValues = Object.keys(sessionStorage).map((key) =>
    sessionStorage.getItem(key),
  );

  for (const value of [...allLocalStorageValues, ...allSessionStorageValues]) {
    expect(value).not.toContain('super-secret-token');
    expect(value).not.toContain(PASSWORD);
  }

  // Only the two permitted keys (§8.1) may exist at all, and neither of
  // them is the credential.
  const localStorageKeys = Object.keys(localStorage);
  for (const key of localStorageKeys) {
    expect(['disp.theme', 'disp.installDismissedAt']).toContain(key);
  }

  vi.restoreAllMocks();
});
