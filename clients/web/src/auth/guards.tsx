import { type ReactElement, type ReactNode, useEffect } from 'react';

import { navigate } from '../lib/navigate';
import type { AuthState } from './authState';
import { useAuth } from './useAuth';

export function isAuthenticated(
  state: AuthState,
): state is Extract<AuthState, { status: 'authenticated' }> {
  return state.status === 'authenticated';
}

export function isAdmin(state: AuthState): boolean {
  return isAuthenticated(state) && state.user.is_admin;
}

interface GuardProps {
  children: ReactNode;
}

/**
 * WEB-SPEC §9: unauthenticated access to a guarded route redirects to
 * /login?next=<pathname+search>. No router exists yet (M04 builds
 * TanStack Router) — this is a router-agnostic interim guard M04 should
 * adopt or reimplement as a route `beforeLoad`; the redirect rule itself
 * (open-redirect-safe `next`, waiting on AuthProvider's bootstrap to have
 * already resolved before judging the state) doesn't change either way.
 */
export function RequireAuth({ children }: GuardProps): ReactElement | null {
  const { state } = useAuth();

  useEffect(() => {
    if (state.status === 'anonymous' || state.status === 'revoked') {
      const next = `${window.location.pathname}${window.location.search}`;
      navigate(`/login?next=${encodeURIComponent(next)}`);
    }
    // `loading` renders nothing below and isn't a real "not authenticated"
    // verdict — AuthProvider itself already blocks children until bootstrap
    // resolves, so this effect won't normally observe `loading` at all.
  }, [state.status]);

  if (!isAuthenticated(state)) {
    return null;
  }
  return <>{children}</>;
}

/**
 * WEB-SPEC §9: a non-admin reaching an admin-only route renders a 403
 * screen — it must NOT redirect, so the URL stays honest about what's
 * there and why it's blocked.
 */
export function RequireAdmin({ children }: GuardProps): ReactElement | null {
  const { state } = useAuth();

  if (!isAuthenticated(state)) {
    return null; // RequireAuth, as the outer guard, is what handles this case.
  }
  if (!state.user.is_admin) {
    return <ForbiddenScreen />;
  }
  return <>{children}</>;
}

function ForbiddenScreen(): ReactElement {
  // Minimal placeholder — M04/M07 will likely give this real styling once
  // the design system (§11) and shell exist.
  return (
    <div role="alert">
      <h1>403 — Forbidden</h1>
      <p>You don&apos;t have permission to view this page.</p>
    </div>
  );
}
