import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';

/**
 * `SchemaForm` calls `useBlocker` (§14.3 rule 7), which needs real router
 * context — a bare RTL `render()` throws. See tests/unit/tiles/testUtils.tsx
 * for the identical pattern and why `router.load()` must be awaited before
 * rendering (the router starts in a `pending` match state).
 */
export async function renderWithRouter(children: ReactNode) {
  const rootRoute = createRootRoute({ component: () => <>{children}</> });
  const router = createRouter({
    routeTree: rootRoute,
    history: createMemoryHistory({ initialEntries: ['/'] }),
  });
  await router.load();
  return { ...render(<RouterProvider router={router} />), router };
}
