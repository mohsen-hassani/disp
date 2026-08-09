import { setUnauthorizedHandler } from '../api/client';
import { authRefresh } from '../api/generated';
import type { AuthRefreshResponse } from '../api/generated';
import { parseProblem } from '../api/problem';
import { navigate } from '../lib/navigate';
import { getAuthState, setAuthState } from './authState';
import { clearToken, getToken, isExpiringWithin, setToken } from './tokenStore';

// WEB-SPEC §8.5: "the timer" is `expires_in - 60s`, minimum 30s.
const PROACTIVE_REFRESH_LEAD_SECONDS = 60;
const MIN_PROACTIVE_REFRESH_SECONDS = 30;

// A custom header, not a WeakSet/Map keyed on the Request object, because
// each retry constructs a brand new (immutable) Request instance — there's
// no single object identity to track "already retried" against across the
// original request and its replay. The header travels with the request
// itself and is never sent to begin with, so this is equivalent in effect
// to "a symbol on the request init" (§8.4 step 4's literal wording) without
// needing external bookkeeping.
const RETRY_HEADER = 'X-Disp-Retried';

// §8.4 step 2: these four paths must never trigger *this* interceptor's own
// refresh-and-retry logic on themselves — doing so would recurse into the
// exact request that's already failing. Bootstrap (§8.3) and the login/
// accept-invite screens (§8.7/§8.8) inspect their own direct call's
// response for core.auth.refresh_token_reused independently of this interceptor.
const NO_RETRY_PATHNAMES = new Set([
  '/api/auth/refresh',
  '/api/auth/login',
  '/api/auth/logout',
  '/api/auth/accept-invite',
]);

type RefreshOutcome = 'ok' | 'failed' | 'reused';

export interface RefreshResult {
  outcome: RefreshOutcome;
  /** Present only when `outcome === 'ok'`. */
  data?: AuthRefreshResponse;
  /** True when the attempt never reached the server (offline/DNS/etc). */
  networkError?: boolean;
}

let proactiveTimer: ReturnType<typeof setTimeout> | null = null;
let inFlightRefresh: Promise<RefreshResult> | null = null;

// Extension point for M04's QueryClient — §8.6's "clear the TanStack Query
// cache" logout step. A no-op until a QueryClient actually exists to clear.
let clearQueryCache: () => void = () => {};
export function setQueryCacheClearer(fn: () => void): void {
  clearQueryCache = fn;
}

export function clearProactiveRefresh(): void {
  if (proactiveTimer !== null) {
    clearTimeout(proactiveTimer);
    proactiveTimer = null;
  }
}

export function scheduleProactiveRefresh(expiresInSeconds: number): void {
  clearProactiveRefresh();
  const delaySeconds = Math.max(
    expiresInSeconds - PROACTIVE_REFRESH_LEAD_SECONDS,
    MIN_PROACTIVE_REFRESH_SECONDS,
  );
  proactiveTimer = setTimeout(() => {
    void getOrStartRefresh();
  }, delaySeconds * 1000);
}

async function performRefresh(): Promise<RefreshResult> {
  const result = await authRefresh();

  if (!result.response) {
    // A true network failure (fetch itself rejected) — nothing to parse as
    // a problem body; treat the same as any other failed refresh attempt.
    return { outcome: 'failed', networkError: true };
  }
  if (result.response.ok && result.data) {
    setToken(result.data.access_token, result.data.expires_in);
    scheduleProactiveRefresh(result.data.expires_in);
    return { outcome: 'ok', data: result.data };
  }

  const problem = parseProblem(result.response, result.error);
  return { outcome: problem.code === 'core.auth.refresh_token_reused' ? 'reused' : 'failed' };
}

// Single-flighted: refresh tokens are one-time-use and rotate on every call,
// so two concurrent callers issuing their own `authRefresh()` would have the
// second one replay an already-rotated cookie, tripping the backend's reuse
// detection and hard-revoking the session. React StrictMode's double-invoked
// mount effect made AuthProvider's bootstrap() do exactly that until it was
// routed through this same guard — every other caller (the 401 interceptor,
// the proactive timer, the visibility-change handler) already went through
// it.
export function getOrStartRefresh(): Promise<RefreshResult> {
  inFlightRefresh ??= performRefresh().finally(() => {
    inFlightRefresh = null;
  });
  return inFlightRefresh;
}

async function purgeApiCaches(): Promise<void> {
  // WEB-SPEC §8.6/§18.3: purge every Cache Storage entry whose URL contains
  // `/api/` on every logout path — a cached response surviving a reload is
  // readable by the next person on a shared device. M09 defines what ends
  // up in these caches in the first place (the service worker's runtime
  // caching rules); this just empties whatever's there.
  if (typeof caches === 'undefined') {
    return;
  }
  const cacheNames = await caches.keys();
  await Promise.all(
    cacheNames.map(async (name) => {
      const cache = await caches.open(name);
      const requests = await cache.keys();
      await Promise.all(
        requests.filter((req) => req.url.includes('/api/')).map((req) => cache.delete(req)),
      );
    }),
  );
}

async function commonLogoutSideEffects(): Promise<void> {
  clearToken();
  clearProactiveRefresh();
  clearQueryCache();
  await purgeApiCaches();
}

/** Soft logout (§8.6): the token was simply invalid/expired. */
export async function softLogout(next?: string): Promise<void> {
  await commonLogoutSideEffects();
  setAuthState({ status: 'anonymous' });
  const suffix = next ? `?next=${encodeURIComponent(next)}` : '';
  navigate(`/login${suffix}`);
}

/** Hard logout (§8.6): refresh-token reuse was detected. */
export async function hardLogout(): Promise<void> {
  await commonLogoutSideEffects();
  setAuthState({ status: 'revoked', reason: 'reuse_detected' });
  navigate('/login');
}

function buildRetryRequest(original: Request): Request {
  const headers = new Headers(original.headers);
  headers.set(RETRY_HEADER, '1');
  const token = getToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  } else {
    headers.delete('Authorization');
  }
  return new Request(original, { headers });
}

/**
 * WEB-SPEC §8.4, the single-flight 401 response interceptor. Registered
 * with M02's client.ts below via setUnauthorizedHandler — client.ts already
 * guarantees this only runs for actual 401 responses.
 */
export async function handleUnauthorizedResponse(
  response: Response,
  request: Request,
): Promise<Response> {
  const { pathname } = new URL(request.url);

  if (NO_RETRY_PATHNAMES.has(pathname)) {
    return response;
  }
  if (request.headers.has(RETRY_HEADER)) {
    return response;
  }

  const { outcome } = await getOrStartRefresh();

  if (outcome === 'reused') {
    await hardLogout();
    return response;
  }
  if (outcome === 'failed') {
    await softLogout();
    return response;
  }

  return fetch(buildRetryRequest(request));
}

setUnauthorizedHandler(handleUnauthorizedResponse);

// WEB-SPEC §8.5: pause the proactive timer while hidden; on return to
// visibility, refresh immediately if the token is already expired or about
// to be, so a phone that's been asleep for an hour doesn't wake up to a
// burst of 401s on its next batch of requests.
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      clearProactiveRefresh();
      return;
    }
    const isAuthenticated = getAuthState().status === 'authenticated';
    if (isAuthenticated && isExpiringWithin(PROACTIVE_REFRESH_LEAD_SECONDS * 1000)) {
      void getOrStartRefresh();
    }
  });
}
