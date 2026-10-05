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

/** Same shape as `tests/unit/plants/testUtils.tsx`'s `renderPlants`, for the `learning` domain. */
export async function renderLearning(children: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  queryClient.setQueryData(
    qk.dashboard.manifest(),
    mockManifest({
      modules: [
        {
          domain: 'learning',
          name: 'Learning',
          version: '1.0.0',
          description: null,
          tiles: [],
          notification_types: [],
          settings_panels: [],
          client_nav: { label: 'Learning', icon: 'book-open', order: 30, routes: [] },
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

export function routedFetch(
  handler: (method: string, path: string, request: Request) => Promise<Response> | Response,
) {
  return async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input as string, init);
    const path = new URL(request.url).pathname;
    return handler(request.method, path, request);
  };
}
