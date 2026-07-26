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
