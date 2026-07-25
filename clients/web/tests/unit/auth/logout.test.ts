import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { logout } from '../../../src/auth/AuthProvider';
import { getAuthState, setAuthState } from '../../../src/auth/authState';
import { setQueryCacheClearer } from '../../../src/auth/refresh';
import { setToken } from '../../../src/auth/tokenStore';
import { setNavigate } from '../../../src/lib/navigate';

beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
});

let fetchSpy: ReturnType<typeof vi.spyOn>;
let navigateSpy: ReturnType<typeof vi.fn<(path: string) => void>>;

function fakeCache(urls: string[]): Cache {
  let entries = [...urls];
  return {
    keys: () => Promise.resolve(entries.map((url) => new Request(url))),
    delete: (req: RequestInfo) => {
      const url = req instanceof Request ? req.url : String(req);
      const before = entries.length;
      entries = entries.filter((u) => u !== url);
      return Promise.resolve(entries.length < before);
    },
  } as unknown as Cache;
}

// Case 11: explicit logout calls the endpoint, clears the query cache, and
// purges every /api/ Cache Storage entry.
it('explicit logout calls the endpoint, clears the query cache, and purges /api/ cache entries', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }));
  navigateSpy = vi.fn<(path: string) => void>();
  setNavigate(navigateSpy);
  setToken('some-token', 300);
  setAuthState({
    status: 'authenticated',
    user: { id: 'u', email: 'a@b.com', display_name: 'A', is_admin: false },
  });

  const clearQueryCacheSpy = vi.fn();
  setQueryCacheClearer(clearQueryCacheSpy);

  const apiCache = fakeCache([
    'https://app.example.com/api/notes',
    'https://app.example.com/api/dashboard/manifest',
  ]);
  const shellCache = fakeCache(['https://app.example.com/index.html']);
  const cacheStorageMock = {
    keys: () => Promise.resolve(['api-cache-v1', 'shell-cache-v1']),
    open: (name: string) => Promise.resolve(name === 'api-cache-v1' ? apiCache : shellCache),
  };
  vi.stubGlobal('caches', cacheStorageMock);

  await logout();

  const logoutCall = fetchSpy.mock.calls.find((call: unknown[]) => {
    const req = call[0] as Request;
    return new URL(req.url).pathname === '/api/auth/logout';
  });
  expect(logoutCall).toBeDefined();

  expect(clearQueryCacheSpy).toHaveBeenCalledTimes(1);

  const remainingApiEntries = await apiCache.keys();
  expect(remainingApiEntries).toHaveLength(0);
  const remainingShellEntries = await shellCache.keys();
  expect(remainingShellEntries).toHaveLength(1); // non-/api/ entries are untouched

  expect(getAuthState()).toEqual({ status: 'anonymous' });
  expect(navigateSpy).toHaveBeenCalledWith('/login');

  vi.unstubAllGlobals();
});

afterEach(() => {
  fetchSpy?.mockRestore();
  vi.unstubAllGlobals();
});
