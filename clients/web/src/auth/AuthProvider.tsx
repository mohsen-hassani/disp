import { useQueryClient } from '@tanstack/react-query';
import { type ReactElement, type ReactNode, useEffect, useRef, useSyncExternalStore } from 'react';

import { authAcceptInvite, authLogin, authLogout, authMe, authRefresh } from '../api/generated';
import type { MeResponse, UserOut } from '../api/generated';
import { type ProblemDetail, parseProblem } from '../api/problem';
import { qk } from '../api/queryKeys';
import { getAuthState, setAuthState, subscribeAuthState } from './authState';
import {
  clearProactiveRefresh,
  scheduleProactiveRefresh,
  softLogout as reactiveSoftLogout,
} from './refresh';
import { setToken } from './tokenStore';

export interface AuthActionError {
  problem: ProblemDetail;
  /** Present only for 429 responses, per the Retry-After header. */
  retryAfterSeconds?: number;
}

export type AuthActionResult = { ok: true } | { ok: false; error: AuthActionError };

function buildActionError(response: Response | undefined, body: unknown): AuthActionError {
  if (!response) {
    return {
      problem: {
        type: 'about:blank',
        title: 'Network error',
        status: 0,
        detail: 'Could not reach the server.',
        instance: '',
        code: 'network_error',
        request_id: '',
      },
    };
  }
  const problem = parseProblem(response, body);
  const retryAfterHeader = response.headers.get('Retry-After');
  const retryAfterSeconds = retryAfterHeader === null ? undefined : Number(retryAfterHeader);
  return {
    problem,
    retryAfterSeconds:
      retryAfterSeconds !== undefined && Number.isFinite(retryAfterSeconds)
        ? retryAfterSeconds
        : undefined,
  };
}

// WEB-SPEC §8.3: the bootstrap sequence. Exported so tests can await it
// directly instead of racing a useEffect.
export async function bootstrap(
  getCachedUser?: () => UserOut | undefined,
  onMeFetched?: (me: MeResponse) => void,
): Promise<void> {
  setAuthState({ status: 'loading' });

  const result = await authRefresh();

  if (result.response?.ok && result.data) {
    setToken(result.data.access_token, result.data.expires_in);
    scheduleProactiveRefresh(result.data.expires_in);

    const me = await authMe();
    if (me.response?.ok && me.data) {
      setAuthState({ status: 'authenticated', user: me.data });
      // §15.1's account screen "reuses qk.auth.me(), don't refetch
      // separately" — this is the one bootstrap path that already has a
      // full `MeResponse` (auth_method included, unlike the plain `UserOut`
      // login/accept-invite store) to seed that cache with. Kept as a
      // plain callback (mirroring `getCachedUser` below) rather than an
      // import of `@tanstack/react-query` here, so `bootstrap()` itself
      // stays state-management-agnostic; only the `AuthProvider` component
      // below actually touches a `QueryClient`.
      onMeFetched?.(me.data);
    } else {
      // /auth/me failing right after a successful refresh shouldn't happen,
      // but the refresh response already carries the user — use it rather
      // than getting stuck in `loading`.
      setAuthState({ status: 'authenticated', user: result.data.user });
    }
    return;
  }

  if (!result.response) {
    // True network failure. Full offline-cache plumbing is M09's job;
    // M03's job is to make the degraded state reachable at all —
    // getCachedUser is the extension point M09 wires a real QueryClient
    // cache lookup into (§8.3 step 6, §18.4).
    const cachedUser = getCachedUser?.();
    if (cachedUser && !navigator.onLine) {
      setAuthState({ status: 'authenticated', user: cachedUser });
      return;
    }
    setAuthState({ status: 'anonymous' });
    return;
  }

  const problem = parseProblem(result.response, result.error);
  if (problem.code === 'auth.refresh_token_reused') {
    setAuthState({ status: 'revoked', reason: 'reuse_detected' });
    return;
  }
  setAuthState({ status: 'anonymous' });
}

// WEB-SPEC §8.7. The login screen calls this and maps `error.problem.code`
// to field/form-level copy itself (§7.3) — this function only performs the
// request and state transition.
export async function login(email: string, password: string): Promise<AuthActionResult> {
  const result = await authLogin({ body: { email, password } });

  if (result.response?.ok && result.data) {
    setToken(result.data.access_token, result.data.expires_in);
    scheduleProactiveRefresh(result.data.expires_in);
    setAuthState({ status: 'authenticated', user: result.data.user });
    return { ok: true };
  }

  return { ok: false, error: buildActionError(result.response, result.error) };
}

// WEB-SPEC §8.8.
export async function acceptInvite(
  token: string,
  displayName: string,
  password: string,
): Promise<AuthActionResult> {
  const result = await authAcceptInvite({
    body: { token, display_name: displayName, password },
  });

  if (result.response?.ok && result.data) {
    setToken(result.data.access_token, result.data.expires_in);
    scheduleProactiveRefresh(result.data.expires_in);
    setAuthState({ status: 'authenticated', user: result.data.user });
    return { ok: true };
  }

  return { ok: false, error: buildActionError(result.response, result.error) };
}

// WEB-SPEC §8.6, explicit logout: call the endpoint, then the same
// soft-logout steps (clear token/cache, purge Cache Storage), then navigate
// to /login with no `next` — reuses refresh.ts's softLogout(), which already
// produces a next-less /login URL when called with no argument.
export async function logout(): Promise<void> {
  await authLogout().catch(() => undefined); // best-effort; log out locally regardless
  await reactiveSoftLogout();
}

/** Acknowledges the persistent security banner (§8.6): revoked → anonymous. */
export function dismissRevoked(): void {
  clearProactiveRefresh();
  setAuthState({ status: 'anonymous' });
}

interface AuthProviderProps {
  children: ReactNode;
  /** See `bootstrap`'s doc — M09's offline-degraded-mode extension point. */
  getCachedUser?: () => UserOut | undefined;
}

function BootstrapSkeleton(): ReactElement {
  // WEB-SPEC §8.3 step 1: a full-page skeleton, never a redirect, never the
  // login screen. M04 owns the real application shell; this placeholder
  // only needs to not be either of those two wrong things.
  return (
    <div aria-busy="true" aria-live="polite" style={{ minHeight: '100vh' }}>
      <span className="sr-only">Loading…</span>
    </div>
  );
}

export function AuthProvider({ children, getCachedUser }: AuthProviderProps): ReactElement {
  const state = useSyncExternalStore(subscribeAuthState, getAuthState);
  const queryClient = useQueryClient();

  // bootstrap() must run exactly once per mount, not whenever a caller
  // passes a fresh getCachedUser function reference — read the latest
  // value through a ref rather than the effect's own dependency array.
  const getCachedUserRef = useRef(getCachedUser);
  getCachedUserRef.current = getCachedUser;

  useEffect(() => {
    void bootstrap(
      () => getCachedUserRef.current?.(),
      (me) => queryClient.setQueryData(qk.auth.me(), me),
    );
    // Deliberately `[]`: bootstrap must run exactly once per mount, and
    // `queryClient` is a stable singleton for the app's lifetime anyway.
  }, []);

  if (state.status === 'loading') {
    return <BootstrapSkeleton />;
  }

  return <>{children}</>;
}
