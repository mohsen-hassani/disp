import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';

import { ToastProvider } from '../../../src/components/feedback/ToastProvider';
import { qk } from '../../../src/api/queryKeys';
import { mockManifest } from '../../mocks/fixtures';

/**
 * Notes components render `<Link>` (row navigation, the overflow menu's
 * "Open") and use TanStack Query — same shape as `tests/unit/tiles/testUtils.tsx`.
 * `router.load()` must be awaited before `render()`: the router starts in a
 * `pending` match state and won't render children until it resolves.
 */
export async function renderNotes(children: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  // §12.2/§13.7: which module domains are reachable is manifest-derived, and
  // `routes/_app.tsx`'s loader guarantees the manifest is in cache before any
  // of this renders. Seeding it here reproduces that guarantee — without it
  // every component under test sees an empty manifest on first paint and
  // renders the correct-but-unhelpful "nothing is navigable" state.
  queryClient.setQueryData(qk.dashboard.manifest(), mockManifest());
  const rootRoute = createRootRoute({
    component: () => (
      <QueryClientProvider client={queryClient}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>
    ),
  });
  const router = createRouter({
    routeTree: rootRoute,
    history: createMemoryHistory({ initialEntries: ['/'] }),
  });
  await router.load();
  return { ...render(<RouterProvider router={router} />), queryClient, router };
}
