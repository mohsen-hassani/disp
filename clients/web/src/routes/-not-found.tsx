import type { ReactElement } from 'react';

// Router-ignored (leading `-`) — see -login.tsx's doc for why. Also reused
// as `_app.settings.$domain.tsx`'s `notFoundComponent`, per §9: an unknown
// `:domain` renders "the 404 screen", not a bespoke one.
export function NotFoundPage(): ReactElement {
  return (
    <main id="main-content">
      <h1>Page not found</h1>
      <p>The page you&apos;re looking for doesn&apos;t exist.</p>
    </main>
  );
}
