import { ShieldAlert } from 'lucide-react';
import { type ReactElement, useSyncExternalStore } from 'react';

import { dismissRevoked } from '../../auth/AuthProvider';
import { getAuthState, subscribeAuthState } from '../../auth/authState';

// WEB-SPEC §8.6/Appendix D: hard logout (auth.refresh_token_reused) sets
// `revoked`, which — unlike `anonymous` — must render a persistent security
// warning that only disappears once the user dismisses it explicitly (or
// signs back in, which navigates away from /login entirely). Mounted only
// on the login screen: `revoked` fails `isAuthenticated`, so `_app.tsx`'s
// guard already sends any guarded-route hit straight back to `/login`.
const REVOKED_COPY =
  "You were signed out because your session token was used twice. If this wasn't you, change your password now.";

export function RevokedBanner(): ReactElement | null {
  const state = useSyncExternalStore(subscribeAuthState, getAuthState);

  if (state.status !== 'revoked') {
    return null;
  }

  return (
    <div
      role="alert"
      className="bg-danger text-accent-text flex items-start justify-between gap-3 px-4 py-3 text-sm"
    >
      <div className="flex items-start gap-2">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>{REVOKED_COPY}</span>
      </div>
      <button
        type="button"
        onClick={() => dismissRevoked()}
        className="focus-visible:outline-accent-text shrink-0 rounded-sm text-sm font-medium underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        Dismiss
      </button>
    </div>
  );
}
