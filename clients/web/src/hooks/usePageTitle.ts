import { useMatches } from '@tanstack/react-router';
import { useSyncExternalStore } from 'react';

// Lets each route declare its own title once, via `staticData: { title }` on
// its `createFileRoute(...)` call, and have both the visible TopBar heading
// and `document.title` (set by __root.tsx) derive from that single source —
// WEB-SPEC §9's per-route document.title requirement, without duplicating
// title strings in a second useEffect per route file.
declare module '@tanstack/react-router' {
  interface StaticDataRouteOption {
    title?: string;
  }
}

const FALLBACK_TITLE = 'DISP';

/**
 * §16.2's detail screen needs a *dynamic* title ("<note title> · DISP") that
 * `staticData` can't express (it's fixed at route-definition time, not
 * per-match). A module-level store, rather than a second competing
 * `useEffect` in the detail page racing __root's own title-setting effect,
 * avoids an ordering bug: React fires child effects before parent effects,
 * so a child-owned `document.title = ...` would be clobbered back to the
 * static fallback by __root's effect running after it in the same commit.
 * Routing the override through this store instead means __root's effect is
 * still the *only* thing that ever writes `document.title`, just reacting
 * to a value that can now come from either source.
 */
let titleOverride: string | null = null;
let listeners: Array<() => void> = [];

function subscribe(onStoreChange: () => void): () => void {
  listeners = [...listeners, onStoreChange];
  return () => {
    listeners = listeners.filter((listener) => listener !== onStoreChange);
  };
}

function getSnapshot(): string | null {
  return titleOverride;
}

/** Call from a route's own `useEffect`, with a cleanup that passes `null` on unmount. */
export function setPageTitleOverride(title: string | null): void {
  titleOverride = title;
  for (const listener of listeners) {
    listener();
  }
}

/** The active override if one is set, else the deepest matched route's declared title, else the fallback. */
export function usePageTitle(): string {
  const override = useSyncExternalStore(subscribe, getSnapshot);
  const matches = useMatches();
  if (override) {
    return override;
  }
  for (let i = matches.length - 1; i >= 0; i--) {
    const title = matches[i]?.staticData.title;
    if (title) {
      return title;
    }
  }
  return FALLBACK_TITLE;
}
