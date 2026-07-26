import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, expect, it } from 'vitest';

import { setAuthState } from '../../../src/auth/authState';
import { AppShell } from '../../../src/components/layout/AppShell';
import { CreateNoteDialogProvider } from '../../../src/components/notes/CreateNoteDialogProvider';
import { ToastProvider } from '../../../src/components/feedback/ToastProvider';
import { qk } from '../../../src/api/queryKeys';
import type { DashboardManifestResponse } from '../../../src/api/generated';
import { TEST_USER } from '../auth/testUtils';

afterEach(() => {
  setAuthState({ status: 'anonymous' });
});

function manifest(): DashboardManifestResponse {
  return {
    platform_version: '0.1.0',
    modules: [
      {
        domain: 'notes',
        name: 'Notes',
        version: '1.0.0',
        description: null,
        tiles: [],
        notification_types: [],
        settings_panels: [],
      },
    ],
  };
}

async function renderShell(children: ReactNode, isAdmin = false) {
  setAuthState({ status: 'authenticated', user: { ...TEST_USER, is_admin: isAdmin } });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  queryClient.setQueryData(qk.dashboard.manifest(), manifest());

  const rootRoute = createRootRoute({
    component: () => (
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <CreateNoteDialogProvider>
            <AppShell>{children}</AppShell>
          </CreateNoteDialogProvider>
        </ToastProvider>
      </QueryClientProvider>
    ),
  });
  const router = createRouter({
    routeTree: rootRoute,
    history: createMemoryHistory({ initialEntries: ['/'] }),
  });
  await router.load();
  return render(<RouterProvider router={router} />);
}

it('renders its children inside the main landmark, plus nav derived from the manifest', async () => {
  await renderShell(<p>Page content</p>);

  expect(screen.getByRole('main')).toHaveTextContent('Page content');
  // Two navs (SideNav + BottomNav) each render a Notes link.
  expect(screen.getAllByRole('link', { name: /notes/i }).length).toBeGreaterThan(0);
});

it('does not render the admin-only Invitations item for a non-admin', async () => {
  await renderShell(<p>Page content</p>, false);
  expect(screen.queryByRole('link', { name: /invitations/i })).not.toBeInTheDocument();
});

it('renders the admin-only Invitations item for an admin', async () => {
  await renderShell(<p>Page content</p>, true);
  expect(screen.getAllByRole('link', { name: /invitations/i }).length).toBeGreaterThan(0);
});

// Proves AppShell itself wires useKeyboardShortcuts up correctly (the hook's
// own dispatch logic is covered in isolation by useKeyboardShortcuts.test.tsx).
it('opens the shortcuts dialog on "?"', async () => {
  const user = userEvent.setup();
  await renderShell(<p>Page content</p>);

  await user.keyboard('?');
  expect(await screen.findByRole('dialog')).toHaveTextContent(/keyboard shortcuts/i);
});
