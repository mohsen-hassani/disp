import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type { PlantOut } from '../../../src/api/generated';
import { PlantList } from '../../../src/components/plants/PlantList';
import { jsonResponse, problemResponse } from '../auth/testUtils';
import { setOnline } from '../pwa/testUtils';
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
  setOnline(true);
});

function plant(overrides: Partial<PlantOut> = {}): PlantOut {
  return {
    id: 'plant-1',
    name: 'Monstera',
    description: null,
    care_notes: null,
    has_image: false,
    image_url: null,
    due_count: 0,
    max_days_overdue: 0,
    next_due_on: '2026-01-10',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function pageResponse(
  items: PlantOut[],
  overrides: Partial<{ next_cursor: string | null; has_more: boolean }> = {},
) {
  return jsonResponse({
    items,
    next_cursor: overrides.next_cursor ?? null,
    has_more: overrides.has_more ?? false,
  });
}

function noop(): void {
  // default no-op prop for callbacks the test doesn't assert on
}

it('renders plants and their due badge', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(pageResponse([plant({ due_count: 2, max_days_overdue: 3 })]));
  await renderPlants(<PlantList q={undefined} onQChange={noop} />);

  expect(await screen.findByText('Monstera')).toBeInTheDocument();
  expect(screen.getByText('Up to 3 days overdue')).toBeInTheDocument();
});

it('debounces the search input before calling onQChange', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(pageResponse([]));
  const onQChange = vi.fn();
  const user = userEvent.setup();
  await renderPlants(<PlantList q={undefined} onQChange={onQChange} />);
  await screen.findByText('No plants yet. Add your first one to start tracking care.');

  await user.type(screen.getByLabelText('Search plants'), 'mon');
  expect(onQChange).not.toHaveBeenCalled();

  await waitFor(() => expect(onQChange).toHaveBeenCalledWith('mon'), { timeout: 1000 });
});

it('shows the no-filters empty state with an add-plant CTA', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(pageResponse([]));
  await renderPlants(<PlantList q={undefined} onQChange={noop} />);

  expect(
    await screen.findByText('No plants yet. Add your first one to start tracking care.'),
  ).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /add your first plant/i })).toBeInTheDocument();
});

it('shows the filtered empty state with a Clear filters button', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(pageResponse([]));
  await renderPlants(<PlantList q="nothing-matches" onQChange={noop} />);

  expect(await screen.findByText('No plants match your search.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /clear filters/i })).toBeInTheDocument();
});

it('shows an error state with a retry button', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(problemResponse(500, 'internal_error'));
  await renderPlants(<PlantList q={undefined} onQChange={noop} />);

  expect(await screen.findByText('Failed to load plants.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
});

it('shows "Showing saved data" when offline and plants are already loaded', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(pageResponse([plant()]));
  setOnline(false);
  await renderPlants(<PlantList q={undefined} onQChange={noop} />);

  await screen.findByText('Monstera');
  expect(screen.getByText('Showing saved data.')).toBeInTheDocument();
});
