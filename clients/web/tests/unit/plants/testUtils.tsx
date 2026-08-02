import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRouter,
} from '@tanstack/react-router';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';

import { ToastProvider } from '../../../src/components/feedback/ToastProvider';
import type {
  CalendarEntry,
  CareIntervalOut,
  CareLogOut,
  DueSummary,
  PlantDetailOut,
  PlantOut,
} from '../../../src/api/generated';

/**
 * Same shape as `tests/unit/notes/testUtils.tsx`: plants components render
 * `<Link>` and use TanStack Query, and `router.load()` must be awaited before
 * `render()` because the router starts in a `pending` match state.
 */
export async function renderPlants(children: ReactNode) {
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

export function plant(overrides: Partial<PlantOut> = {}): PlantOut {
  return {
    id: 'plant-1',
    name: 'Sansevieria',
    description: null,
    care_notes: null,
    has_image: false,
    image_url: null,
    due_count: 0,
    max_days_overdue: 0,
    next_due_on: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

export function plantDetail(overrides: Partial<PlantDetailOut> = {}): PlantDetailOut {
  return { ...plant(), intervals: [], ...overrides };
}

export function interval(overrides: Partial<CareIntervalOut> = {}): CareIntervalOut {
  return {
    id: 'interval-1',
    plant_id: 'plant-1',
    name: 'Water',
    interval_days: 15,
    next_due_on: '2026-03-16',
    last_done_on: '2026-03-01',
    active: true,
    days_overdue: -15,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

export function careLog(overrides: Partial<CareLogOut> = {}): CareLogOut {
  return {
    id: 'log-1',
    plant_id: 'plant-1',
    interval_id: 'interval-1',
    action_name: 'Water',
    due_on: '2026-03-01',
    completed_on: '2026-03-03',
    days_late: 2,
    note: null,
    created_at: '2026-03-03T00:00:00Z',
    ...overrides,
  };
}

export function dueSummary(overrides: Partial<DueSummary> = {}): DueSummary {
  return {
    day: '2026-03-01',
    count: 0,
    overdue_count: 0,
    max_days_overdue: 0,
    summary: 'Nothing due today',
    items: [],
    ...overrides,
  };
}

export function calendarEntry(overrides: Partial<CalendarEntry> = {}): CalendarEntry {
  return {
    day: '2026-03-16',
    kind: 'due',
    plant_id: 'plant-1',
    plant_name: 'Sansevieria',
    interval_id: 'interval-1',
    action_name: 'Water',
    log_id: null,
    days_late: null,
    ...overrides,
  };
}
