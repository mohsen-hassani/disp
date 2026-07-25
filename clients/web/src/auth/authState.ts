import type { UserOut } from '../api/generated';

// WEB-SPEC §8.2, exact shape. `revoked` is a distinct state from
// `anonymous` specifically because it must produce a visible security
// warning, not a silent redirect — don't collapse the two.
export type AuthState =
  | { status: 'loading' }
  | { status: 'anonymous' }
  | { status: 'authenticated'; user: UserOut }
  | { status: 'revoked'; reason: 'reuse_detected' };

let state: AuthState = { status: 'loading' };
const listeners = new Set<() => void>();

// A plain module-scoped external store, not React Context: refresh.ts's
// response interceptor runs outside any component (it's registered on
// M02's client.ts at module load) and needs to transition auth state —
// e.g. into `revoked` on reuse detection — without depending on React.
// useAuth.ts subscribes to this via useSyncExternalStore.
export function getAuthState(): AuthState {
  return state;
}

export function setAuthState(next: AuthState): void {
  state = next;
  for (const listener of listeners) {
    listener();
  }
}

export function subscribeAuthState(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
