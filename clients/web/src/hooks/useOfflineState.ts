import { useEffect, useState } from 'react';

import { useOnlineStatus } from './useOnlineStatus';

const POLL_INTERVAL_MS = 30_000;

/**
 * §18.5: `navigator.onLine`/the `online`/`offline` events are the primary
 * signal, but browsers report `onLine` optimistically (a live network
 * interface with no real route to this server still reads "online"). While
 * offline, a periodic `HEAD /health/live` (confirmed cheap — no DB access)
 * can flip the state back to online *before* the browser's own `online`
 * event fires, if it turns out we can already reach the backend again.
 * Skipped while the tab is hidden (the milestone's own resolved open
 * question) — polling an invisible tab drains battery for no visible
 * benefit.
 */
export function useOfflineState(): boolean {
  const browserOnline = useOnlineStatus();
  const [confirmedOffline, setConfirmedOffline] = useState(!browserOnline);

  useEffect(() => {
    setConfirmedOffline(!browserOnline);
  }, [browserOnline]);

  useEffect(() => {
    if (browserOnline) {
      return undefined;
    }

    let cancelled = false;
    function poll(): void {
      if (document.hidden) {
        return;
      }
      fetch('/health/live', { method: 'HEAD', cache: 'no-store' })
        .then((response) => {
          if (!cancelled && response.ok) {
            setConfirmedOffline(false);
          }
        })
        .catch(() => {
          // Still unreachable — stay offline, try again next tick.
        });
    }

    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [browserOnline]);

  return confirmedOffline;
}
