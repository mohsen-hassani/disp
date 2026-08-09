import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type { CareIntervalOut } from '../../../src/api/generated';
import { IntervalList } from '../../../src/components/plants/IntervalList';
import { jsonResponse, problemResponse, pathnameOf } from '../auth/testUtils';
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
    interval_days: 7,
    next_due_on: '2026-01-08',
    last_done_on: '2026-01-01',
    active: true,
    days_overdue: -7,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

it('renders "No care intervals yet." when the plant has none', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch');
  await renderPlants(<IntervalList plantId="plant-1" intervals={[]} />);
  expect(screen.getByText('No care intervals yet.')).toBeInTheDocument();
});

it('adds a new interval with the entered name and cadence', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(
      jsonResponse(interval({ id: 'interval-2', name: 'Fertilize', interval_days: 30 }), {
        status: 201,
      }),
    );
  const user = userEvent.setup();
  await renderPlants(<IntervalList plantId="plant-1" intervals={[]} />);

  await user.click(screen.getByRole('button', { name: /add interval/i }));
  const dialog = await screen.findByRole('dialog');
  await user.type(within(dialog).getByLabelText(/name/i), 'Fertilize');
  const daysInput = within(dialog).getByLabelText(/repeat every/i);
  await user.clear(daysInput);
  await user.type(daysInput, '30');
  await user.click(within(dialog).getByRole('button', { name: /^add interval$/i }));

  await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
  const request = fetchSpy.mock.calls[0]?.[0] as Request;
  expect(pathnameOf(request)).toBe('/api/plants/plant-1/intervals');
  const body = await request.clone().json();
  expect(body).toEqual({ name: 'Fertilize', interval_days: 30, last_done_on: undefined });
});

it('surfaces a future last_done_on rejection inline on that field', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(
      problemResponse(400, 'plants.future_date', {
        detail: 'last_done_on cannot be in the future.',
      }),
    );
  const user = userEvent.setup();
  await renderPlants(<IntervalList plantId="plant-1" intervals={[]} />);

  await user.click(screen.getByRole('button', { name: /add interval/i }));
  const dialog = await screen.findByRole('dialog');
  await user.type(within(dialog).getByLabelText(/name/i), 'Water');
  await user.click(within(dialog).getByRole('button', { name: /^add interval$/i }));

  expect(await screen.findByText('last_done_on cannot be in the future.')).toBeInTheDocument();
});

it('edits an existing interval, sending the updated name and cadence', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(jsonResponse(interval({ name: 'Water thoroughly' })));
  const user = userEvent.setup();
  await renderPlants(<IntervalList plantId="plant-1" intervals={[interval()]} />);

  await user.click(screen.getByRole('button', { name: /more actions for "water"/i }));
  await user.click(await screen.findByText('Edit'));
  const dialog = await screen.findByRole('dialog');
  const nameInput = within(dialog).getByLabelText(/name/i);
  await user.clear(nameInput);
  await user.type(nameInput, 'Water thoroughly');
  await user.click(within(dialog).getByRole('button', { name: /^save$/i }));

  await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
  const request = fetchSpy.mock.calls[0]?.[0] as Request;
  expect(request.method).toBe('PATCH');
  expect(pathnameOf(request)).toBe('/api/plants/plant-1/intervals/interval-1');
});

it('deletes an interval after confirming', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  const user = userEvent.setup();
  await renderPlants(<IntervalList plantId="plant-1" intervals={[interval()]} />);

  await user.click(screen.getByRole('button', { name: /more actions for "water"/i }));
  await user.click(await screen.findByText('Delete'));
  await user.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: /^delete interval$/i }),
  );

  await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
  const request = fetchSpy.mock.calls[0]?.[0] as Request;
  expect(request.method).toBe('DELETE');
  expect(pathnameOf(request)).toBe('/api/plants/plant-1/intervals/interval-1');
});
