import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';

import { qk } from '../../../src/api/queryKeys';
import { ToastProvider } from '../../../src/components/feedback/ToastProvider';
import { mockManifest } from '../../mocks/fixtures';

/**
 * Same shape as `tests/unit/notes/testUtils.tsx`'s `renderNotes` — plants
 * components render `<Link>` (row navigation, edit) and use TanStack Query.
 * `router.load()` must be awaited before `render()`: the router starts in a
 * `pending` match state and won't render children until it resolves.
 */
export async function renderPlants(children: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  // §12.2/§13.7: which module domains are reachable is manifest-derived, and
  // `routes/_app.tsx`'s loader guarantees the manifest is in cache before any
  // of this renders — reproduced here the same way `renderNotes` does.
  queryClient.setQueryData(
    qk.dashboard.manifest(),
    mockManifest({
      modules: [
        {
          domain: 'plants',
          name: 'Plants',
          version: '1.0.0',
          description: null,
          tiles: [],
          notification_types: [],
          settings_panels: [],
          client_nav: { label: 'Plants', icon: 'sprout', order: 20, routes: [] },
        },
      ],
    }),
  );
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
