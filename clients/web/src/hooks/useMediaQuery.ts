import { useCallback, useSyncExternalStore } from 'react';

/**
 * `useSyncExternalStore`-based, so it stays correct if the query never
 * changes between renders (avoids the classic `useEffect` + `useState`
 * media-query hook's one-frame-stale-on-mount flash) and works safely
 * under React 19 concurrent rendering.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      const mql = window.matchMedia(query);
      mql.addEventListener('change', onStoreChange);
      return () => mql.removeEventListener('change', onStoreChange);
    },
    [query],
  );
  const getSnapshot = useCallback(() => window.matchMedia(query).matches, [query]);

  return useSyncExternalStore(subscribe, getSnapshot);
}
