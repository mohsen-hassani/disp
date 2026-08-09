import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { PlantNewPage } from '../../../src/routes/-plant-new';
import { jsonResponse, problemResponse } from '../auth/testUtils';
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

it('creates a plant and navigates to its detail screen', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    jsonResponse(
      {
        id: 'plant-new',
        name: 'Fiddle Leaf Fig',
        description: null,
        care_notes: null,
        has_image: false,
        image_url: null,
        due_count: 0,
        max_days_overdue: 0,
        next_due_on: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      { status: 201 },
    ),
  );
  const user = userEvent.setup();
  const { router } = await renderPlants(<PlantNewPage />);

  await user.type(screen.getByLabelText(/^name/i), 'Fiddle Leaf Fig');
  await user.click(screen.getByRole('button', { name: /create plant/i }));

  await waitFor(() => expect(router.state.location.pathname).toBe('/plants/plant-new'));
});

it('maps a 422 name conflict onto the name field', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    new Response(
      JSON.stringify({
        type: 'about:blank',
        title: 'Validation error',
        status: 422,
        detail: 'Invalid request.',
        instance: '/api/plants',
        code: 'validation_error',
        request_id: 'req-1',
        errors: [{ loc: ['body', 'name'], msg: 'Name is required.', type: 'value_error' }],
      }),
      { status: 422, headers: { 'Content-Type': 'application/json' } },
    ),
  );
  const user = userEvent.setup();
  await renderPlants(<PlantNewPage />);

  await user.type(screen.getByLabelText(/^name/i), 'X');
  await user.click(screen.getByRole('button', { name: /create plant/i }));

  expect(await screen.findByText('Name is required.')).toBeInTheDocument();
});

it('shows a generic error toast-worthy message for a non-field error', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(problemResponse(500, 'internal_error'));
  const user = userEvent.setup();
  await renderPlants(<PlantNewPage />);

  await user.type(screen.getByLabelText(/^name/i), 'Fern');
  await user.click(screen.getByRole('button', { name: /create plant/i }));

  expect(await screen.findByText(/something went wrong on the server/i)).toBeInTheDocument();
});
