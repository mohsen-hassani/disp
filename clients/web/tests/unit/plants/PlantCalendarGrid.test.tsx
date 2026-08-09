import { render, screen } from '@testing-library/react';
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { expect, it } from 'vitest';

import type { CalendarEntry } from '../../../src/api/generated';
import { PlantCalendarGrid } from '../../../src/components/plants/PlantCalendarGrid';

async function renderGrid(entries: CalendarEntry[]) {
  const rootRoute = createRootRoute({
    component: () => <PlantCalendarGrid month="2026-08" entries={entries} />,
  });
  const router = createRouter({
    routeTree: rootRoute,
    history: createMemoryHistory({ initialEntries: ['/'] }),
  });
  await router.load();
  return render(<RouterProvider router={router} />);
}

function entry(overrides: Partial<CalendarEntry> = {}): CalendarEntry {
  return {
    day: '2026-08-15',
    kind: 'due',
    plant_id: 'plant-1',
    plant_name: 'Monstera',
    interval_id: 'interval-1',
    action_name: 'Water',
    ...overrides,
  };
}

it('renders one entry link per day', async () => {
  await renderGrid([entry()]);
  expect(screen.getByRole('link', { name: 'Monstera' })).toBeInTheDocument();
});

// Case 5 (M14 §7): a `projected` entry must be visually distinguished from
// a real `due` entry — asserted on the actual class list (the greyed-out
// tone), not just that both render, so a regression that makes them look
// identical would fail this test.
it('renders a projected entry with a visually distinct (greyed-out) class from a due entry', async () => {
  await renderGrid([
    entry({ kind: 'due', plant_name: 'Due Plant', interval_id: 'due-interval' }),
    entry({ kind: 'projected', plant_name: 'Projected Plant', interval_id: 'projected-interval' }),
  ]);

  const dueLink = screen.getByRole('link', { name: 'Due Plant' });
  const projectedLink = screen.getByRole('link', { name: 'Projected Plant' });

  expect(dueLink.className).not.toBe(projectedLink.className);
  expect(projectedLink.className).toContain('opacity-60');
  expect(dueLink.className).not.toContain('opacity-60');
});

it('shows an overflow count beyond the per-day visible limit', async () => {
  await renderGrid([
    entry({ interval_id: 'a', plant_name: 'A' }),
    entry({ interval_id: 'b', plant_name: 'B' }),
    entry({ interval_id: 'c', plant_name: 'C' }),
    entry({ interval_id: 'd', plant_name: 'D' }),
  ]);

  expect(screen.getByText('+1 more')).toBeInTheDocument();
});
