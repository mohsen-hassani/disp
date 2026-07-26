import type { ErrorComponentProps } from '@tanstack/react-router';
import type { ReactElement } from 'react';

// §20.2 level 2: wired as the router's `defaultErrorComponent` (main.tsx) —
// each matched route gets its own boundary, so a leaf route's render crash
// only replaces that route's own slot inside `<Outlet/>`. `AppShell`
// (top bar, side/bottom nav) is rendered by the parent `_app` route around
// that `<Outlet/>`, so it's a sibling of this fallback, not a descendant —
// it stays mounted and usable automatically.
export function RouteErrorFallback({ reset }: ErrorComponentProps): ReactElement {
  return (
    <div className="border-border bg-surface flex flex-col items-start gap-3 rounded-md border border-dashed p-8">
      <h2 className="text-text text-base font-medium">This page hit an error.</h2>
      <p className="text-text-muted text-sm">
        The rest of DISP is still usable — try again, or navigate elsewhere.
      </p>
      <button
        type="button"
        onClick={reset}
        className="bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        Retry
      </button>
    </div>
  );
}
