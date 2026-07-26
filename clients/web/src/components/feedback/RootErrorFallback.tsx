import type { ReactElement } from 'react';

// §20.2 level 1: the outermost boundary (wraps the whole tree in main.tsx),
// for a render crash nothing more specific caught — the router hasn't
// necessarily even mounted, so this can't assume a shell/nav exists to fall
// back into. Reload is a hard `location.reload()`, not `reset()`, since a
// crash this high up may mean app state itself is broken.
export function RootErrorFallback(): ReactElement {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-text text-lg font-semibold">Something went wrong.</h1>
      <p className="text-text-muted max-w-sm text-sm">
        DISP hit an unexpected error and couldn&apos;t continue. Reloading usually fixes this.
      </p>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        Reload
      </button>
      <p className="text-text-muted text-xs">Version {__APP_VERSION__}</p>
    </div>
  );
}
