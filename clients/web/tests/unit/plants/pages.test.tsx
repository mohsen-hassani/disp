import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { PlantCalendarPage } from '../../../src/routes/-plant-calendar';
import { PlantDetailPage } from '../../../src/routes/-plant-detail';
import { PlantsListPage } from '../../../src/routes/-plants';
import { jsonResponse } from '../auth/testUtils';
import {
  calendarEntry,
  careLog,
  dueSummary,
  interval,
  plant,
  plantDetail,
  renderPlants,
} from './testUtils';

beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
});

let fetchSpy: ReturnType<typeof vi.spyOn>;
afterEach(() => {
  fetchSpy?.mockRestore();
});

/**
 * These screens fire several queries at once, so a call-order-based mock is
 * flaky by construction. Routing on the URL instead makes each test state
 * what each endpoint returns. Patterns are matched in insertion order, so
 * the most specific path must come first.
 */
function mockApi(routes: Array<[string, () => Response]>): ReturnType<typeof vi.spyOn> {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = typeof input === 'string' ? input : (input as Request).url;
    for (const [pattern, make] of routes) {
      if (url.includes(pattern)) return make();
    }
    return new Response(null, { status: 404 });
  });
}

function page(items: unknown[]): Response {
  return jsonResponse({ items, next_cursor: null, has_more: false });
}

function noop(): void {
  // callback the test doesn't assert on
}

// --------------------------------------------------------------------------
// PlantsListPage
// --------------------------------------------------------------------------

it('lists plants and leads with the due summary when work is outstanding', async () => {
  fetchSpy = mockApi([
    [
      '/api/plants/due',
      () =>
        jsonResponse(
          dueSummary({
            count: 2,
            overdue_count: 1,
            max_days_overdue: 2,
            summary: '2 actions due, up to 2 days behind',
          }),
        ),
    ],
    ['/api/plants', () => page([plant({ name: 'Sansevieria', due_count: 2 })])],
  ]);

  await renderPlants(<PlantsListPage onQChange={noop} />);

  await waitFor(() =>
    expect(screen.getByText('2 actions due, up to 2 days behind')).toBeInTheDocument(),
  );
  expect(screen.getByText('Sansevieria')).toBeInTheDocument();
});

it('says nothing about due work when there is none', async () => {
  fetchSpy = mockApi([
    ['/api/plants/due', () => jsonResponse(dueSummary())],
    ['/api/plants', () => page([plant()])],
  ]);

  await renderPlants(<PlantsListPage onQChange={noop} />);
  await waitFor(() => expect(screen.getByText('Sansevieria')).toBeInTheDocument());
  expect(screen.queryByText('Nothing due today')).not.toBeInTheDocument();
});

it('offers a first-plant call to action when the list is empty', async () => {
  fetchSpy = mockApi([
    ['/api/plants/due', () => jsonResponse(dueSummary())],
    ['/api/plants', () => page([])],
  ]);

  await renderPlants(<PlantsListPage onQChange={noop} />);
  await waitFor(() => expect(screen.getByText('No plants yet')).toBeInTheDocument());
  expect(screen.getByRole('button', { name: 'Add your first plant' })).toBeInTheDocument();
});

it('distinguishes an empty search from an empty collection', async () => {
  fetchSpy = mockApi([
    ['/api/plants/due', () => jsonResponse(dueSummary())],
    ['/api/plants', () => page([])],
  ]);

  await renderPlants(<PlantsListPage q="fern" onQChange={noop} />);
  await waitFor(() => expect(screen.getByText(/No plants match/)).toBeInTheDocument());
  expect(screen.queryByRole('button', { name: 'Add your first plant' })).not.toBeInTheDocument();
});

it('offers a retry when the list fails to load', async () => {
  fetchSpy = mockApi([
    ['/api/plants/due', () => jsonResponse(dueSummary())],
    ['/api/plants', () => new Response(null, { status: 500 })],
  ]);

  await renderPlants(<PlantsListPage onQChange={noop} />);
  await waitFor(() => expect(screen.getByText('Could not load your plants.')).toBeInTheDocument());
  expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
});

it('pushes the debounced search term up to the route', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    fetchSpy = mockApi([
      ['/api/plants/due', () => jsonResponse(dueSummary())],
      ['/api/plants', () => page([])],
    ]);
    const onQChange = vi.fn();
    await renderPlants(<PlantsListPage onQChange={onQChange} />);

    await userEvent.type(screen.getByLabelText('Search plants'), 'fern');
    await vi.advanceTimersByTimeAsync(400);

    await waitFor(() => expect(onQChange).toHaveBeenCalledWith('fern'));
  } finally {
    vi.useRealTimers();
  }
});

// --------------------------------------------------------------------------
// PlantDetailPage
// --------------------------------------------------------------------------

it('shows a plant with its schedule, notes and history', async () => {
  fetchSpy = mockApi([
    [
      '/history',
      () => jsonResponse([careLog({ action_name: 'Water', completed_on: '2026-03-03' })]),
    ],
    [
      '/api/plants/plant-1',
      () =>
        jsonResponse(
          plantDetail({
            care_notes: 'Bright indirect light.',
            intervals: [interval({ name: 'Water', days_overdue: 2 })],
          }),
        ),
    ],
  ]);

  await renderPlants(<PlantDetailPage plantId="plant-1" />);

  await waitFor(() =>
    expect(screen.getByRole('heading', { name: 'Sansevieria' })).toBeInTheDocument(),
  );
  expect(screen.getByLabelText('Care notes')).toHaveValue('Bright indirect light.');
  expect(screen.getByText('2 days behind')).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText(/2026-03-03/)).toBeInTheDocument());
});

it('keeps Save disabled until something actually changes', async () => {
  fetchSpy = mockApi([
    ['/history', () => jsonResponse([])],
    ['/api/plants/plant-1', () => jsonResponse(plantDetail())],
  ]);

  await renderPlants(<PlantDetailPage plantId="plant-1" />);
  await waitFor(() =>
    expect(screen.getByRole('heading', { name: 'Sansevieria' })).toBeInTheDocument(),
  );

  const save = screen.getByRole('button', { name: /Save changes/ });
  expect(save).toBeDisabled();

  await userEvent.type(screen.getByLabelText('Care notes'), 'Water sparingly.');
  expect(save).toBeEnabled();
});

it('says when nothing has been logged yet', async () => {
  fetchSpy = mockApi([
    ['/history', () => jsonResponse([])],
    ['/api/plants/plant-1', () => jsonResponse(plantDetail())],
  ]);

  await renderPlants(<PlantDetailPage plantId="plant-1" />);
  await waitFor(() => expect(screen.getByText('Nothing logged yet.')).toBeInTheDocument());
});

it('requires confirmation before deleting a plant', async () => {
  fetchSpy = mockApi([
    ['/history', () => jsonResponse([])],
    ['/api/plants/plant-1', () => jsonResponse(plantDetail())],
  ]);

  await renderPlants(<PlantDetailPage plantId="plant-1" />);
  await waitFor(() =>
    expect(screen.getByRole('heading', { name: 'Sansevieria' })).toBeInTheDocument(),
  );

  await userEvent.click(screen.getByRole('button', { name: 'Delete plant' }));
  expect(screen.getByText(/Delete Sansevieria and its whole schedule\?/)).toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.queryByText(/and its whole schedule/)).not.toBeInTheDocument();
});

// --------------------------------------------------------------------------
// PlantCalendarPage
// --------------------------------------------------------------------------

function calendarResponse(entries: unknown[], month = '2026-03'): Response {
  return jsonResponse({ month, start: `${month}-01`, end: `${month}-31`, entries });
}

it('renders a month with its entries and legend', async () => {
  fetchSpy = mockApi([
    [
      '/api/plants/calendar',
      () => calendarResponse([calendarEntry({ day: '2026-03-18', action_name: 'Water' })]),
    ],
  ]);

  await renderPlants(<PlantCalendarPage month="2026-03" onMonthChange={noop} />);

  await waitFor(() => expect(screen.getByTitle(/Water — Sansevieria/)).toBeInTheDocument());
  expect(screen.getByRole('heading', { name: /March 2026/ })).toBeInTheDocument();
  expect(screen.getByText('projected')).toBeInTheDocument();
});

it('steps between months', async () => {
  fetchSpy = mockApi([['/api/plants/calendar', () => calendarResponse([])]]);
  const onMonthChange = vi.fn();

  await renderPlants(<PlantCalendarPage month="2026-03" onMonthChange={onMonthChange} />);
  await waitFor(() => expect(screen.getByText('projected')).toBeInTheDocument());

  await userEvent.click(screen.getByRole('button', { name: 'Previous month' }));
  expect(onMonthChange).toHaveBeenCalledWith('2026-02');

  await userEvent.click(screen.getByRole('button', { name: 'Next month' }));
  expect(onMonthChange).toHaveBeenCalledWith('2026-04');
});

it('offers a jump back to today only when looking at another month', async () => {
  fetchSpy = mockApi([['/api/plants/calendar', () => calendarResponse([])]]);

  await renderPlants(<PlantCalendarPage month="2019-01" onMonthChange={noop} />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Today' })).toBeInTheDocument());
});

it('offers a retry when the calendar fails to load', async () => {
  fetchSpy = mockApi([['/api/plants/calendar', () => new Response(null, { status: 500 })]]);

  await renderPlants(<PlantCalendarPage month="2026-03" onMonthChange={noop} />);
  await waitFor(() => expect(screen.getByText('Could not load the calendar.')).toBeInTheDocument());
});

it('opens the create dialog from the list header', async () => {
  fetchSpy = mockApi([
    ['/api/plants/due', () => jsonResponse(dueSummary())],
    ['/api/plants', () => page([plant()])],
  ]);

  await renderPlants(<PlantsListPage onQChange={noop} />);
  await waitFor(() => expect(screen.getByText('Sansevieria')).toBeInTheDocument());

  await userEvent.click(screen.getByRole('button', { name: /New plant/ }));
  expect(await screen.findByRole('dialog')).toBeInTheDocument();
  expect(screen.getByLabelText('Name')).toBeInTheDocument();
});

it('opens the create dialog from the empty state', async () => {
  fetchSpy = mockApi([
    ['/api/plants/due', () => jsonResponse(dueSummary())],
    ['/api/plants', () => page([])],
  ]);

  await renderPlants(<PlantsListPage onQChange={noop} />);
  await waitFor(() => expect(screen.getByText('No plants yet')).toBeInTheDocument());

  await userEvent.click(screen.getByRole('button', { name: 'Add your first plant' }));
  expect(await screen.findByRole('dialog')).toBeInTheDocument();
});
