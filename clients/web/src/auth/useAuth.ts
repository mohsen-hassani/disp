import { useSyncExternalStore } from 'react';

import { acceptInvite, dismissRevoked, login, logout } from './AuthProvider';
import { type AuthState, getAuthState, subscribeAuthState } from './authState';

export interface UseAuthResult {
  state: AuthState;
  login: typeof login;
  logout: typeof logout;
  acceptInvite: typeof acceptInvite;
  dismissRevoked: typeof dismissRevoked;
}

/**
 * The one hook screens use for both auth state and auth actions. Returns
 * `state` as a discriminated union (narrow on `state.status`) rather than
 * spreading its fields, so TypeScript can still narrow `state.user` etc.
 * correctly at call sites.
 */
export function useAuth(): UseAuthResult {
  const state = useSyncExternalStore(subscribeAuthState, getAuthState);
  return { state, login, logout, acceptInvite, dismissRevoked };
}
