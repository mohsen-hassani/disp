import type { QueryClient } from '@tanstack/react-query';
import { createRootRouteWithContext, Outlet, useRouterState } from '@tanstack/react-router';
import { useEffect, useRef } from 'react';

import { usePageTitle } from '../hooks/usePageTitle';

export interface RouterContext {
  queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootComponent,
});

function RootComponent() {
  const title = usePageTitle();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const announceRef = useRef<HTMLDivElement>(null);
  // Tracks the previous pathname rather than a one-shot "is this the first
  // render" boolean: React 19 StrictMode double-invokes effects in dev,
  // which would consume a boolean flag on the phantom first invocation and
  // leave the real one thinking it's a "later" navigation. Comparing
  // against the last-seen pathname is idempotent under that double-invoke
  // (same pathname twice never reads as a change) and still correctly
  // detects a real navigation, including the redirect `_app`'s guard
  // performs before this component's very first paint.
  const previousPathnameRef = useRef<string | null>(null);

  useEffect(() => {
    document.title = title;
  }, [title]);

  useEffect(() => {
    if (announceRef.current) {
      announceRef.current.textContent = title;
    }

    // §21 A9: route changes move focus to the page's <h1> — but not on the
    // very first paint, where focus belongs at the document default (so a
    // keyboard user tabbing from the browser chrome lands on the skip link
    // first, per A10, rather than being yanked into the middle of the page).
    const isRealNavigation =
      previousPathnameRef.current !== null && previousPathnameRef.current !== pathname;
    previousPathnameRef.current = pathname;
    if (!isRealNavigation) {
      return;
    }
    const heading = document.querySelector<HTMLElement>('main h1');
    if (heading) {
      heading.tabIndex = -1;
      heading.focus();
    }
  }, [pathname, title]);

  return (
    <>
      <a
        href="#main-content"
        className="bg-accent text-accent-text focus-visible:outline-accent sr-only rounded-md px-4 py-2 focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        Skip to content
      </a>
      {/* §21 A9: visually hidden live region announcing the new page title. */}
      <div ref={announceRef} role="status" aria-live="polite" className="sr-only" />
      <Outlet />
    </>
  );
}
