import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type { CareIntervalOut, PlantDetailOut } from '../../../src/api/generated';
import { qk } from '../../../src/api/queryKeys';
import { PlantDetailPage } from '../../../src/routes/-plant-detail';
import { dateOnly } from '../../../src/lib/format';
import { jsonResponse, problemResponse } from '../auth/testUtils';
import { mockCareLog } from '../../mocks/fixtures';
import { renderPlants } from './testUtils';

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

function interval(overrides: Partial<CareIntervalOut> = {}): CareIntervalOut {
  return {
    id: 'interval-1',
    plant_id: 'plant-1',
    name: 'Water',
    interval_days: 15,
    next_due_on: '2026-01-01',
    last_done_on: '2025-12-17',
    active: true,
    days_overdue: 15,
    created_at: '2025-12-01T00:00:00Z',
    updated_at: '2025-12-17T00:00:00Z',
    ...overrides,
  };
}

function plantDetail(overrides: Partial<PlantDetailOut> = {}): PlantDetailOut {
  return {
    id: 'plant-1',
    name: 'Monstera',
    description: null,
    care_notes: null,
    has_image: false,
    image_url: null,
    due_count: 1,
    max_days_overdue: 15,
    next_due_on: '2026-01-01',
    created_at: '2025-12-01T00:00:00Z',
    updated_at: '2025-12-01T00:00:00Z',
    intervals: [interval()],
    ...overrides,
  };
}

/**
 * Routes by method+path rather than call order, so an automatic background
 * refetch (from an actively-observed query being invalidated) doesn't have
 * to land in a fixed position in the call sequence to be handled correctly.
 * `current` is mutated by the `complete` handler so a refetch after
 * completion sees the same state the mutation response already carried —
 * matching a real backend, where the two are never out of sync.
 */
function stateFullFetch(
  initialInterval: CareIntervalOut,
  completeHandler: (request: Request) => Promise<Response>,
) {
  let current = initialInterval;
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const request = input instanceof Request ? input : new Request(input as string, init);
    const path = new URL(request.url).pathname;

    if (request.method === 'GET' && path === '/api/plants/plant-1') {
      return jsonResponse(plantDetail({ intervals: [current] }));
    }
    if (request.method === 'GET' && path === '/api/plants/plant-1/history') {
      return jsonResponse([mockCareLog()]);
    }
    if (request.method === 'POST' && path === '/api/plants/plant-1/intervals/interval-1/complete') {
      const response = await completeHandler(request);
      if (response.ok) {
        const cloned = (await response.clone().json()) as { interval: CareIntervalOut };
        current = cloned.interval;
      }
      return response;
    }
    if (request.method === 'DELETE' && path === '/api/plants/plant-1') {
      return new Response(null, { status: 204 });
    }
    throw new Error(`Unhandled request in test: ${request.method} ${path}`);
  });
}

it('renders the plant, its due badge, and its care interval', async () => {
  fetchSpy = stateFullFetch(interval(), async () => new Response(null, { status: 500 }));
  await renderPlants(<PlantDetailPage plantId="plant-1" />);

  expect(await screen.findByRole('heading', { name: 'Monstera' })).toBeInTheDocument();
  expect(screen.getByText('Up to 15 days overdue')).toBeInTheDocument();
  expect(screen.getByText('Water')).toBeInTheDocument();
  expect(screen.getByText('15 days overdue')).toBeInTheDocument();
});

// Case 1 (M14 §7): completing renders the *server's* returned `next_due_on`
// — a client-side `due_on + interval_days` would land on 2026-01-16; the
// server (completion-date-based, M14 §1) returns 2026-01-18. Asserting
// against `dateOnly` (the same formatter the component uses) instead of a
// hand-written string keeps the assertion locale-independent, not a
// coincidence of matching the production code's own output.
it('renders the server-recomputed next_due_on after completing, not a client computation', async () => {
  const recomputed = interval({
    days_overdue: -18,
    next_due_on: '2026-01-18',
    last_done_on: '2026-01-03',
  });
  fetchSpy = stateFullFetch(interval(), async (request) => {
    const body = (await request.clone().json()) as { completed_on?: string; note?: string };
    expect(body.completed_on).toBe('2026-01-03');
    return jsonResponse(
      {
        log: mockCareLog({ completed_on: '2026-01-03', due_on: '2026-01-01' }),
        interval: recomputed,
      },
      { status: 201 },
    );
  });
  const user = userEvent.setup();
  await renderPlants(<PlantDetailPage plantId="plant-1" />);
  await screen.findByText('15 days overdue');

  await user.click(screen.getByRole('button', { name: /mark done/i }));
  const dialog = await screen.findByRole('dialog');
  // Case 2: back-dating sends `completed_on` and reschedules from it.
  // `fireEvent.change` (not `user.type`) — jsdom's `<input type="date">`
  // doesn't support userEvent's segment-by-segment keyboard typing.
  fireEvent.change(within(dialog).getByLabelText(/completed on/i), {
    target: { value: '2026-01-03' },
  });
  await user.click(within(dialog).getByRole('button', { name: /^mark done$/i }));

  await waitFor(() => expect(screen.queryByText('15 days overdue')).not.toBeInTheDocument());
  expect(screen.getByText(`Due ${dateOnly('2026-01-18')}`)).toBeInTheDocument();
});

// Case 3 (M14 §7): a 400 on a future/too-old `completed_on` surfaces inline
// on the date field, and the note text the user already typed survives —
// the dialog doesn't reset the form on a rejected submit.
it('surfaces a future-date rejection inline without losing the note field', async () => {
  fetchSpy = stateFullFetch(interval(), async () =>
    problemResponse(400, 'modules.plants.future_date', { detail: 'completed_on cannot be in the future.' }),
  );
  const user = userEvent.setup();
  await renderPlants(<PlantDetailPage plantId="plant-1" />);
  await screen.findByText('15 days overdue');

  await user.click(screen.getByRole('button', { name: /mark done/i }));
  const dialog = await screen.findByRole('dialog');
  await user.type(within(dialog).getByLabelText(/note/i), 'Watered it a bit early.');
  fireEvent.change(within(dialog).getByLabelText(/completed on/i), {
    target: { value: '2099-01-01' },
  });
  await user.click(within(dialog).getByRole('button', { name: /^mark done$/i }));

  expect(await screen.findByText('completed_on cannot be in the future.')).toBeInTheDocument();
  expect(within(dialog).getByLabelText(/note/i)).toHaveValue('Watered it a bit early.');
});

// Case 6 (M14 §7): every plants mutation invalidates the dashboard tile —
// checked directly against the query cache rather than the UI, since the
// dashboard tile isn't mounted on this screen.
it('invalidates the plants.due dashboard tile after completing an interval', async () => {
  fetchSpy = stateFullFetch(interval(), async () =>
    jsonResponse(
      { log: mockCareLog(), interval: interval({ days_overdue: -10 }) },
      { status: 201 },
    ),
  );
  const user = userEvent.setup();
  const { queryClient } = await renderPlants(<PlantDetailPage plantId="plant-1" />);
  await screen.findByText('15 days overdue');
  queryClient.setQueryData(qk.dashboard.tile('plants.due'), { key: 'plants.due' });

  await user.click(screen.getByRole('button', { name: /mark done/i }));
  const dialog = await screen.findByRole('dialog');
  await user.click(within(dialog).getByRole('button', { name: /^mark done$/i }));

  await waitFor(() =>
    expect(queryClient.getQueryState(qk.dashboard.tile('plants.due'))?.isInvalidated).toBe(true),
  );
});

it('deleting confirms, then navigates back to the list', async () => {
  fetchSpy = stateFullFetch(interval(), async () => new Response(null, { status: 500 }));
  const user = userEvent.setup();
  const { router } = await renderPlants(<PlantDetailPage plantId="plant-1" />);
  await screen.findByRole('heading', { name: 'Monstera' });

  // Exact match: the interval row's own "More actions for "Water"" trigger
  // also matches a loose /more actions/i regex.
  await user.click(screen.getByRole('button', { name: 'More actions' }));
  await user.click(await screen.findByText('Delete'));
  await user.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: /^delete plant$/i }),
  );

  await waitFor(() => expect(router.state.location.pathname).toBe('/plants'));
});
