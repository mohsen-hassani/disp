import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { client, setAccessTokenGetter } from '../../../src/api/client';
import { authRefresh, healthLive } from '../../../src/api/generated/sdk.gen';

function jsonResponse(body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('api/client request interceptor', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  // The real app relies on relative URLs resolving against the browser's
  // document location (§2.1) — that's what an empty baseUrl is for. Node's
  // native `Request` (used here under Vitest+jsdom, since jsdom itself has no
  // fetch/Request implementation of its own) has no such document to resolve
  // against and requires an absolute URL, unlike a real browser. This is a
  // test-environment-only accommodation, not a production behavior change.
  beforeAll(() => {
    client.setConfig({ baseUrl: 'http://localhost' });
  });

  afterAll(() => {
    client.setConfig({ baseUrl: '' });
  });

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse());
    setAccessTokenGetter(() => null);
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it('does not add X-Requested-With to a non-auth request', async () => {
    await healthLive();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const request = fetchSpy.mock.calls[0]![0] as Request;
    expect(new URL(request.url).pathname).toBe('/health/live');
    expect(request.headers.get('X-Requested-With')).toBeNull();
  });

  it('adds X-Requested-With: disp to /api/auth/refresh exactly (not the spec’s literal "mystuff")', async () => {
    await authRefresh();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const request = fetchSpy.mock.calls[0]![0] as Request;
    expect(new URL(request.url).pathname).toBe('/api/auth/refresh');
    expect(request.headers.get('X-Requested-With')).toBe('disp');
  });

  it('omits the Authorization header when no token is held', async () => {
    setAccessTokenGetter(() => null);

    await healthLive();

    const request = fetchSpy.mock.calls[0]![0] as Request;
    expect(request.headers.has('Authorization')).toBe(false);
  });

  it('adds Authorization: Bearer <token> once a token getter is registered', async () => {
    setAccessTokenGetter(() => 'test-access-token');

    await healthLive();

    const request = fetchSpy.mock.calls[0]![0] as Request;
    expect(request.headers.get('Authorization')).toBe('Bearer test-access-token');
  });
});
