import { useEffect } from 'react';

/**
 * WEB-SPEC §13.4: pausing `refetchInterval` while hidden (via TanStack
 * Query's own `refetchIntervalInBackground: false` on the caller's
 * `useQuery`) is necessary but not sufficient — on returning to visibility,
 * a query whose interval already elapsed while hidden must refetch
 * immediately rather than wait for the next tick. This hook is that resume
 * half; the pause half is the caller's `useQuery` config.
 */
export function useIntervalRefresh(params: {
  dataUpdatedAt: number;
  intervalMs: number;
  refetch: () => void;
}): void {
  const { dataUpdatedAt, intervalMs, refetch } = params;

  useEffect(() => {
    function handleVisibilityChange(): void {
      if (document.hidden) {
        return;
      }
      if (Date.now() - dataUpdatedAt >= intervalMs) {
        refetch();
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [dataUpdatedAt, intervalMs, refetch]);
}
