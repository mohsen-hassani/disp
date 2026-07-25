import { useSyncExternalStore } from 'react';

function subscribe(onStoreChange: () => void): () => void {
  window.addEventListener('online', onStoreChange);
  window.addEventListener('offline', onStoreChange);
  return () => {
    window.removeEventListener('online', onStoreChange);
    window.removeEventListener('offline', onStoreChange);
  };
}

function getSnapshot(): boolean {
  return navigator.onLine;
}

/**
 * WEB-SPEC §18.5's OfflineBanner (M09) is the primary consumer — created
 * now, per M04's scope, so that milestone doesn't need its own plumbing
 * for something this generic. `navigator.onLine` is optimistic (a browser
 * can report "online" while actually unable to reach anything); M09's
 * periodic `HEAD /health/live` check compensates for that. This hook only
 * reports the browser's own signal.
 */
export function useOnlineStatus(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot);
}
