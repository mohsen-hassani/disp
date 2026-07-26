import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { setOnline } from './testUtils';

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

// Case 44: "A mutation attempted offline is blocked in the UI and issues no
// request." Enforced once, generically, in api/client.ts's fetch
// implementation — every mutating call (POST/PATCH/PUT/DELETE) goes
// through it. The generated client's own pipeline catches the resulting
// rejection and resolves with `{ error, response: undefined }` — the exact
// shape every existing "no response" handling path (AuthProvider,
// useTileAction, etc.) already checks for a genuine network failure.
it('blocks a POST while offline without ever calling fetch', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch');
  setOnline(false);

  const { response, error } = await client.post({ url: '/api/notes', body: { body: 'test' } });

  expect(response).toBeUndefined();
  expect(error).toBeInstanceOf(TypeError);
  expect(fetchSpy).not.toHaveBeenCalled();
});

it.each(['PATCH', 'PUT', 'DELETE'] as const)(
  'blocks a %s while offline without calling fetch',
  async (method) => {
    fetchSpy = vi.spyOn(globalThis, 'fetch');
    setOnline(false);

    const { response } = await client.request({ method, url: '/api/notes/note-1' });

    expect(response).toBeUndefined();
    expect(fetchSpy).not.toHaveBeenCalled();
  },
);

it('still issues GET requests while offline, for the service worker cache fallback', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(
      new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
  setOnline(false);

  await client.get({ url: '/api/notes' });

  expect(fetchSpy).toHaveBeenCalled();
});

it('allows a POST through once back online', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(
      new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
  setOnline(true);

  await client.post({ url: '/api/notes', body: { body: 'test' } });

  expect(fetchSpy).toHaveBeenCalled();
});
