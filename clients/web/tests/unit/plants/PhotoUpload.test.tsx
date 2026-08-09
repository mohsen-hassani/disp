import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type { PlantDetailOut } from '../../../src/api/generated';
import { PhotoUpload } from '../../../src/components/plants/PhotoUpload';
import { jsonResponse, pathnameOf } from '../auth/testUtils';
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

function plant(overrides: Partial<PlantDetailOut> = {}): PlantDetailOut {
  return {
    id: 'plant-1',
    name: 'Monstera',
    description: null,
    care_notes: null,
    has_image: false,
    image_url: null,
    due_count: 0,
    max_days_overdue: 0,
    next_due_on: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    intervals: [],
    ...overrides,
  };
}

it('rejects an unsupported file type client-side, without calling the API', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch');
  await renderPlants(<PhotoUpload plant={plant()} />);

  const file = new File(['not an image'], 'notes.txt', { type: 'text/plain' });
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  // `userEvent.upload` itself filters files against the input's `accept`
  // attribute and silently drops a mismatched one — bypassed here with a
  // direct `files` assignment + `change` event, the same way a real browser
  // still allows a mismatched file through an "All files" picker option.
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  fireEvent.change(input);

  expect(await screen.findByText('Choose a JPEG, PNG, WebP or GIF image.')).toBeInTheDocument();
  expect(fetchSpy).not.toHaveBeenCalled();
});

it('rejects an oversized file client-side, without calling the API', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch');
  const user = userEvent.setup();
  await renderPlants(<PhotoUpload plant={plant()} />);

  const file = new File(['x'], 'big.jpg', { type: 'image/jpeg' });
  Object.defineProperty(file, 'size', { value: 3 * 1024 * 1024 });
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await user.upload(input, file);

  expect(await screen.findByText(/too large/)).toBeInTheDocument();
  expect(fetchSpy).not.toHaveBeenCalled();
});

it('uploads a valid file via PUT to the plant image endpoint', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(jsonResponse(plant({ has_image: true })));
  const user = userEvent.setup();
  await renderPlants(<PhotoUpload plant={plant()} />);

  const file = new File(['image-bytes'], 'monstera.jpg', { type: 'image/jpeg' });
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await user.upload(input, file);

  await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
  const request = fetchSpy.mock.calls[0]?.[0] as Request;
  expect(request.method).toBe('PUT');
  expect(pathnameOf(request)).toBe('/api/plants/plant-1/image');
});

it('removes the photo via DELETE when "Remove photo" is clicked', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  const user = userEvent.setup();
  await renderPlants(
    <PhotoUpload plant={plant({ has_image: true, image_url: '/api/plants/plant-1/image' })} />,
  );

  await user.click(screen.getByRole('button', { name: /remove photo/i }));

  await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
  const request = fetchSpy.mock.calls[0]?.[0] as Request;
  expect(request.method).toBe('DELETE');
  expect(pathnameOf(request)).toBe('/api/plants/plant-1/image');
});
