import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { bootstrap } from '../../../src/auth/AuthProvider';
import { getAuthState, setAuthState } from '../../../src/auth/authState';
import { clearProactiveRefresh } from '../../../src/auth/refresh';
import { clearToken, getToken } from '../../../src/auth/tokenStore';
import { loginResponse, meResponse, problemResponse, TEST_USER } from './testUtils';

// See M02's client.test.ts: Node's native Request needs an absolute URL,
// unlike a real browser resolving relative URLs against document.location.
beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
});

let fetchSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  fetchSpy = vi.spyOn(globalThis, 'fetch');
  setAuthState({ status: 'loading' });
  clearToken();
  clearProactiveRefresh();
});

afterEach(() => {
  fetchSpy.mockRestore();
  clearProactiveRefresh();
  vi.useRealTimers();
});

// Case 1: successful refresh yields `authenticated`.
it('bootstrap: successful refresh yields authenticated with the resolved user', async () => {
  fetchSpy.mockResolvedValueOnce(loginResponse()).mockResolvedValueOnce(meResponse());

  await bootstrap();

  const state = getAuthState();
  expect(state.status).toBe('authenticated');
  if (state.status === 'authenticated') {
    expect(state.user).toMatchObject(TEST_USER);
  }
  expect(getToken()).toBe('test-access-token');
});

// Case 2: a plain 401 yields `anonymous`.
it('bootstrap: a 401 without the reuse code yields anonymous', async () => {
  fetchSpy.mockResolvedValueOnce(problemResponse(401, 'core.auth.invalid_refresh_token'));

  await bootstrap();

  expect(getAuthState()).toEqual({ status: 'anonymous' });
  expect(getToken()).toBeNull();
});

// Case 3: auth.refresh_token_reused yields `revoked`.
it('bootstrap: auth.refresh_token_reused yields revoked', async () => {
  fetchSpy.mockResolvedValueOnce(problemResponse(401, 'core.auth.refresh_token_reused'));

  await bootstrap();

  expect(getAuthState()).toEqual({ status: 'revoked', reason: 'reuse_detected' });
});

// §8.3 step 6/§18.4: a true network failure (no response at all) while
// offline with a cached user available degrades to authenticated read-only,
// rather than bouncing to the login screen.
it('bootstrap: a network failure while offline with a cached user yields authenticated', async () => {
  fetchSpy.mockRejectedValueOnce(new TypeError('Failed to fetch'));
  const onlineSpy = vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);

  await bootstrap(() => TEST_USER);

  expect(getAuthState()).toEqual({ status: 'authenticated', user: TEST_USER });
  onlineSpy.mockRestore();
});

it('bootstrap: a network failure with no cached user (or while online) yields anonymous', async () => {
  fetchSpy.mockRejectedValueOnce(new TypeError('Failed to fetch'));

  await bootstrap();

  expect(getAuthState()).toEqual({ status: 'anonymous' });
});

// Case 13: proactive refresh fires at expires_in - 60s, not before.
it('schedules the next refresh at expires_in - 60s and fires it then', async () => {
  vi.useFakeTimers();
  fetchSpy
    .mockResolvedValueOnce(loginResponse({ expires_in: 300 }))
    .mockResolvedValueOnce(meResponse());

  await bootstrap();

  const refreshCallsSoFar = fetchSpy.mock.calls.length;

  await vi.advanceTimersByTimeAsync(239_000); // 300 - 60 = 240s; one second short
  expect(fetchSpy.mock.calls.length).toBe(refreshCallsSoFar);

  fetchSpy.mockResolvedValueOnce(loginResponse({ expires_in: 300 }));
  await vi.advanceTimersByTimeAsync(1_000); // crosses the 240s mark
  expect(fetchSpy.mock.calls.length).toBe(refreshCallsSoFar + 1);
});
