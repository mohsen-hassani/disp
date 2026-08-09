import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { setAuthState } from '../../../src/auth/authState';
import { setNavigate } from '../../../src/lib/navigate';
import { handleUnauthorizedResponse } from '../../../src/auth/refresh';
import { clearToken, isExpiringWithin, setToken } from '../../../src/auth/tokenStore';
import { loginResponse, problemResponse } from './testUtils';

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
  setAuthState({
    status: 'authenticated',
    user: { id: 'u', email: 'a@b.com', display_name: 'A', is_admin: false },
  });
  clearToken();
});

afterEach(() => {
  fetchSpy.mockRestore();
  vi.useRealTimers();
});

function requestTo(pathname: string, extraHeaders: HeadersInit = {}): Request {
  return new Request(`http://localhost${pathname}`, { headers: extraHeaders });
}

// Case 9: a 401 on /auth/refresh itself does not recurse.
it('does not attempt a refresh when the failing request is /auth/refresh itself', async () => {
  const original401 = problemResponse(401, 'core.auth.invalid_refresh_token');
  const request = requestTo('/api/auth/refresh');

  const result = await handleUnauthorizedResponse(original401, request);

  expect(result).toBe(original401);
  expect(fetchSpy).not.toHaveBeenCalled();
});

// Case 10: an already-retried-once request is not retried again.
it('does not retry a request that already carries the retry marker', async () => {
  const original401 = problemResponse(401, 'core.auth.invalid_token');
  const request = requestTo('/api/notes', { 'X-Disp-Retried': '1' });

  const result = await handleUnauthorizedResponse(original401, request);

  expect(result).toBe(original401);
  expect(fetchSpy).not.toHaveBeenCalled();
});

// Case 8: three concurrent 401s share exactly one refresh call and all
// three original requests are replayed.
it('single-flights a refresh across three concurrent 401s and replays all three', async () => {
  fetchSpy.mockImplementation((input: RequestInfo | URL) => {
    const url = input instanceof Request ? input.url : String(input);
    if (new URL(url).pathname === '/api/auth/refresh') {
      return Promise.resolve(loginResponse({ access_token: 'fresh-token' }));
    }
    return Promise.resolve(new Response('{}', { status: 200 }));
  });

  const original401 = problemResponse(401, 'core.auth.invalid_token');
  const requests = [requestTo('/api/notes'), requestTo('/api/notes/1'), requestTo('/api/notes/2')];

  const results = await Promise.all(
    requests.map((req) => handleUnauthorizedResponse(original401, req)),
  );

  const refreshCalls = fetchSpy.mock.calls.filter((call: unknown[]) => {
    const input = call[0];
    const url = input instanceof Request ? input.url : String(input);
    return new URL(url).pathname === '/api/auth/refresh';
  });
  expect(refreshCalls).toHaveLength(1);

  // Each of the three originals was replayed (status 200 from the mock
  // above, not the original 401), proving the retry actually happened.
  for (const result of results) {
    expect(result.status).toBe(200);
    expect(result).not.toBe(original401);
  }

  // The replayed requests carry the fresh token, not whatever was set (or
  // absent) before the refresh.
  const replayedNotesCall = fetchSpy.mock.calls.find((call: unknown[]) => {
    const req = call[0] as Request;
    return req.url.includes('/api/notes') && req.headers.get('X-Disp-Retried') === '1';
  });
  expect(replayedNotesCall).toBeDefined();
  const replayedRequest = replayedNotesCall![0] as Request;
  expect(replayedRequest.headers.get('Authorization')).toBe('Bearer fresh-token');
});

it('hard-logs-out on auth.refresh_token_reused instead of retrying', async () => {
  fetchSpy.mockResolvedValueOnce(problemResponse(401, 'core.auth.refresh_token_reused'));

  const original401 = problemResponse(401, 'core.auth.invalid_token');
  const result = await handleUnauthorizedResponse(original401, requestTo('/api/notes'));

  expect(result).toBe(original401);
  const { getAuthState } = await import('../../../src/auth/authState');
  expect(getAuthState()).toEqual({ status: 'revoked', reason: 'reuse_detected' });
});

it('soft-logs-out when the refresh attempt itself fails for an unrelated reason', async () => {
  fetchSpy.mockResolvedValueOnce(problemResponse(401, 'core.auth.invalid_refresh_token'));

  const original401 = problemResponse(401, 'core.auth.invalid_token');
  const result = await handleUnauthorizedResponse(original401, requestTo('/api/notes'));

  expect(result).toBe(original401);
  const { getAuthState } = await import('../../../src/auth/authState');
  expect(getAuthState()).toEqual({ status: 'anonymous' });
});

// Case 14: returning to visibility with an expiring/expired token refreshes
// immediately.
it('refreshes on visibilitychange when the token is already expiring', async () => {
  setToken('old-token', 10); // expires in 10s — within the 60s lead window
  expect(isExpiringWithin(60_000)).toBe(true);

  fetchSpy.mockResolvedValueOnce(loginResponse({ access_token: 'woken-up-token' }));

  Object.defineProperty(document, 'hidden', { value: false, configurable: true });
  document.dispatchEvent(new Event('visibilitychange'));

  // The listener kicks off an async refresh (fetch isn't called until a few
  // microtask ticks in) — flush the microtask queue before asserting.
  await new Promise((resolve) => setTimeout(resolve, 0));

  expect(fetchSpy).toHaveBeenCalledTimes(1);
  const [input] = fetchSpy.mock.calls[0]!;
  const req = input as Request;
  expect(new URL(req.url).pathname).toBe('/api/auth/refresh');
});
