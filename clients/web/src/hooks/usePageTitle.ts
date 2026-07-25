import { useMatches } from '@tanstack/react-router';

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

/** The deepest matched route's declared title, or the fallback if none set one. */
export function usePageTitle(): string {
  const matches = useMatches();
  for (let i = matches.length - 1; i >= 0; i--) {
    const title = matches[i]?.staticData.title;
    if (title) {
      return title;
    }
  }
  return FALLBACK_TITLE;
}
