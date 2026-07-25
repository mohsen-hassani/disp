import { setAccessTokenGetter } from '../api/client';

// WEB-SPEC §8.1, exact shape. Module-scoped variables, not React state —
// the token must not trigger re-renders on its own and must be readable
// from client.ts's interceptor without a hook. Never write the access
// token here to localStorage/sessionStorage/IndexedDB/Cache API/a
// JS-set cookie/the URL — this file is the only place the in-memory token
// lives at all.
let accessToken: string | null = null;
let expiresAt: number | null = null;

export function setToken(token: string, expiresInSeconds: number): void {
  accessToken = token;
  expiresAt = Date.now() + expiresInSeconds * 1000;
}

export function getToken(): string | null {
  return accessToken;
}

export function clearToken(): void {
  accessToken = null;
  expiresAt = null;
}

export function isExpiringWithin(ms: number): boolean {
  if (accessToken === null || expiresAt === null) {
    return true;
  }
  return expiresAt - Date.now() <= ms;
}

// Wires this store into M02's client.ts extension point so the
// Authorization header interceptor can read the token directly.
setAccessTokenGetter(getToken);
