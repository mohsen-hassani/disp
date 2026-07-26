import { WifiOff } from 'lucide-react';
import type { ReactElement } from 'react';

import { useOfflineState } from '../../hooks/useOfflineState';

/**
 * §18.5: appears at the top of the shell whenever offline, disappears with
 * no reload on reconnect (TanStack Query's `refetchOnReconnect` default —
 * §10.1 — refreshes everything once `useOnlineStatus`'s `online` event
 * fires). `role="status"`/`aria-live="polite"` rather than `alert` — this
 * is an ambient condition, not something that needs to interrupt whatever
 * the user is doing.
 */
export function OfflineBanner(): ReactElement | null {
  const isOffline = useOfflineState();

  if (!isOffline) {
    return null;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="bg-danger text-accent-text flex items-center justify-center gap-2 px-4 py-2 text-sm"
    >
      <WifiOff className="h-4 w-4" aria-hidden="true" />
      You&apos;re offline. Showing saved data — changes require a connection.
    </div>
  );
}
