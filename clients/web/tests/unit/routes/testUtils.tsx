import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';

import { ToastProvider } from '../../../src/components/feedback/ToastProvider';

/** Account/tokens/invites use TanStack Query and toasts, but no routing (no `Link`, no `useBlocker`). */
export function renderWithProviders(children: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    ...render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>,
    ),
    queryClient,
  };
}
