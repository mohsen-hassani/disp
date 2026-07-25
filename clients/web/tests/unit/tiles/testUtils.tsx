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
 * Tile components render `<Link>` (§13.7's href translation) and use
 * TanStack Query, so a bare RTL `render()` isn't enough — this wraps both
 * a real (memory-history) router and a fresh `QueryClient` per call, the
 * way `main.tsx` composes the real app.
 */
export async function renderTile(children: ReactNode) {
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
  // The router starts in a `pending` match state; RouterProvider renders
  // nothing until it resolves. `render()` alone doesn't wait for that (no
  // loader here means it resolves on a microtask, not synchronously), so
  // every caller must `await` this helper.
  await router.load();
  return { ...render(<RouterProvider router={router} />), queryClient };
}
