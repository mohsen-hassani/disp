import { act } from '@testing-library/react';

/**
 * Toggles `navigator.onLine` and fires the matching `online`/`offline`
 * event, mirroring a real browser transition. Wrapped in `act()` — the
 * listeners this triggers (`useSyncExternalStore` in `useOnlineStatus`, a
 * plain `useState` update in `useOfflineState`) run outside React's own
 * event handling, so without it the resulting re-render isn't flushed
 * before the next assertion runs.
 */
export function setOnline(online: boolean): void {
  act(() => {
    Object.defineProperty(window.navigator, 'onLine', {
      value: online,
      writable: true,
      configurable: true,
    });
    window.dispatchEvent(new Event(online ? 'online' : 'offline'));
  });
}
