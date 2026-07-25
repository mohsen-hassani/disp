import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { TileActionButton } from '../../../src/components/tiles/TileActionButton';
import { makeTileAction } from './fixtures';
import { renderTile } from './testUtils';

beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
});

let fetchSpy: ReturnType<typeof vi.spyOn> | undefined;
afterEach(() => {
  fetchSpy?.mockRestore();
  fetchSpy = undefined;
});

// Test 20 (first half): no body_schema, non-DELETE fires immediately.
it('fires a non-DELETE action without body_schema immediately, with no confirmation', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }));
  const action = makeTileAction({ method: 'POST', path: '/api/notes', label: 'Quick add' });
  const user = userEvent.setup();
  await renderTile(<TileActionButton action={action} tileKey="demo.tile" />);

  await user.click(screen.getByRole('button', { name: /quick add/i }));

  await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

// Test 20 (second half): DELETE confirms first.
it('confirms before firing a DELETE action', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }));
  const action = makeTileAction({ method: 'DELETE', path: '/api/notes/1', label: 'Remove' });
  const user = userEvent.setup();
  await renderTile(<TileActionButton action={action} tileKey="demo.tile" />);

  await user.click(screen.getByRole('button', { name: /^remove$/i }));
  expect(fetchSpy).not.toHaveBeenCalled();

  const dialog = await screen.findByRole('dialog');
  await user.click(within(dialog).getByRole('button', { name: /^remove$/i }));

  await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
});
