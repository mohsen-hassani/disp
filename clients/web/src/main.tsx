import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createRouter, RouterProvider } from '@tanstack/react-router';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { isProblem } from './api/problem';
import { AuthProvider } from './auth/AuthProvider';
import { setQueryCacheClearer } from './auth/refresh';
import { setNavigate } from './lib/navigate';
import { routeTree } from './routeTree.gen';
import './styles/index.css';

// WEB-SPEC §10.1, verbatim.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: (failureCount, error) => !isProblem(error) && failureCount < 2,
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
      throwOnError: false,
    },
    mutations: { retry: false },
  },
});

// §8.6's "clear the TanStack Query cache" logout step — refresh.ts (M03)
// exposed this as a no-op extension point specifically because it runs
// before a QueryClient exists to clear; this is where one finally does.
setQueryCacheClearer(() => queryClient.clear());

const router = createRouter({
  routeTree,
  context: { queryClient },
  scrollRestoration: true,
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

// lib/navigate.ts's swappable primitive defaults to a full-page reload
// (M03's only option before a router existed); every auth transition
// (login, accept-invite, logout, session-revoked) calls `navigate()`, so
// wiring it to the router here is what turns those into client-side
// navigations without touching auth/ itself.
setNavigate((path) => void router.navigate({ href: path }));

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element #root not found');
}

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
