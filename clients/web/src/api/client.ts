import { client } from './generated/client.gen';

// WEB-SPEC §7.1.
const REQUEST_TIMEOUT_MS = 15_000;

let getAccessToken: () => string | null = () => null;

/**
 * Registered by M03's tokenStore/AuthProvider. api/ can't import auth/
 * directly (auth/ depends on api/, not the reverse), so the token getter is
 * wired in at runtime instead of imported at module-load time.
 */
export function setAccessTokenGetter(getter: () => string | null): void {
  getAccessToken = getter;
}

export type UnauthorizedHandler = (response: Response, request: Request) => Promise<Response>;

let handleUnauthorized: UnauthorizedHandler | null = null;

/**
 * Registered by M03's refresh.ts. The single-flight state machine (in-flight
 * dedupe, retry-once tracking, the auth.refresh_token_reused hard-logout
 * branch, §8.4) lives entirely there — until it's wired up, a 401 just
 * passes through unchanged rather than silently swallowing it.
 */
export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  handleUnauthorized = handler;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method) {
    return init.method.toUpperCase();
  }
  if (input instanceof Request) {
    return input.method;
  }
  return 'GET';
}

/**
 * WEB-SPEC §18.1/§18.5, test case 44: mutations require a connection, and
 * an offline attempt must "issue no request" — not merely fail after
 * issuing one. Enforced here, once, for every mutation in the app (every
 * generated SDK call and `useTileAction`'s raw `client.request()` both
 * funnel through this one `fetch` implementation), rather than teaching
 * every mutating button its own offline check. GET/HEAD are exempt: an
 * offline *read* must still be attempted so the service worker's
 * NetworkFirst runtime caching (§18.2) can serve it from cache — blocking
 * those here would break read-only-offline entirely.
 *
 * The rejection mirrors a genuine network failure (a real offline `fetch()`
 * already rejects with a `TypeError` today) rather than a new failure shape.
 * The generated client's own pipeline catches it and resolves with
 * `{ error, response: undefined }` — every existing "no response" handling
 * path (AuthProvider, useTileAction's `toActionError`, etc.) already
 * branches on exactly that.
 */
function isBlockedOffline(input: RequestInfo | URL, init?: RequestInit): boolean {
  if (navigator.onLine) {
    return false;
  }
  const method = requestMethod(input, init);
  return method !== 'GET' && method !== 'HEAD';
}

/**
 * A fresh AbortSignal.timeout() per call, combined with any caller-supplied
 * signal — a single shared signal instance would only fire once for
 * whichever request happens to be in flight when its deadline elapses, not
 * apply a rolling per-request timeout to every request.
 */
function fetchWithTimeout(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  if (isBlockedOffline(input, init)) {
    return Promise.reject(new TypeError('Failed to fetch: offline, mutation blocked.'));
  }
  const timeoutSignal = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  const signal = init?.signal ? AbortSignal.any([init.signal, timeoutSignal]) : timeoutSignal;
  return fetch(input, { ...init, signal });
}

// §7.1 says `baseUrl: '/api'`, but that assumes operation paths are relative
// (e.g. `/auth/refresh`). This backend's OpenAPI document already emits each
// operation's full absolute path exactly as mounted — `/api/auth/refresh`,
// but plain `/health/live` with no `/api` prefix (confirmed directly against
// openapi.json) — so a non-empty baseUrl would double up to
// `/api/api/auth/refresh` and wrongly prefix the health routes. An empty
// baseUrl lets each operation's own path resolve relative to the current
// origin, which is what §2.1's same-origin requirement wants anyway.
client.setConfig({
  baseUrl: '',
  credentials: 'same-origin',
  fetch: fetchWithTimeout,
});

// §7.1: Authorization header present only when a token is actually held —
// never send `Authorization: Bearer null`/`Bearer undefined`.
client.interceptors.request.use((request) => {
  const token = getAccessToken();
  if (token) {
    request.headers.set('Authorization', `Bearer ${token}`);
  } else {
    request.headers.delete('Authorization');
  }

  // §7.1 + M00's spec-vs-reality correction: the backend's CSRF check
  // (src/disp/core/auth/routes.py's _require_csrf_header) requires this
  // exact value on refresh/logout. The spec's literal text says "mystuff",
  // which the real backend rejects outright.
  const { pathname } = new URL(request.url);
  if (pathname === '/api/auth/refresh' || pathname === '/api/auth/logout') {
    request.headers.set('X-Requested-With', 'disp');
  }

  return request;
});

// §8.4's 401 refresh flow — the extension point M03 hooks into.
client.interceptors.response.use(async (response, request) => {
  if (response.status !== 401 || !handleUnauthorized) {
    return response;
  }
  return handleUnauthorized(response, request);
});

export { client };
