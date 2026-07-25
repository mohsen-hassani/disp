import type { ReactElement } from 'react';

import type { AuthState } from './authState';

export function isAuthenticated(
  state: AuthState,
): state is Extract<AuthState, { status: 'authenticated' }> {
  return state.status === 'authenticated';
}

export function isAdmin(state: AuthState): boolean {
  return isAuthenticated(state) && state.user.is_admin;
}

/**
 * WEB-SPEC §9: unauthenticated access to a guarded route redirects to
 * `/login?next=...` — that's now `routes/_app.tsx`'s `beforeLoad` (a router
 * redirect, reachable before any route component ever mounts). The one
 * guard that can't move there is this one: a non-admin reaching `/admin/*`
 * renders a 403 **in place** rather than redirecting, so the URL stays
 * honest about what's there — `beforeLoad` can only throw a redirect or
 * `notFound()`, neither of which fits "render this exact route, blocked".
 * `routes/_app.admin.invites.tsx` calls `isAdmin` itself and renders this.
 */
export function ForbiddenScreen(): ReactElement {
  return (
    <div role="alert">
      <h1>403 — Forbidden</h1>
      <p>You don&apos;t have permission to view this page.</p>
    </div>
  );
}
