import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { TileActionButton } from '../../../src/components/tiles/TileActionButton';
import { setOnline } from '../pwa/testUtils';
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
  setOnline(true);
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

// Case 42: §18.5 "all mutating controls are disabled while offline" applies
// to tile actions too, not just notes — every trigger variant this
// component renders (plain, DELETE-confirm, body_schema-dialog) must
// disable itself.
it('disables every trigger variant while offline, with the tooltip (case 42)', async () => {
  setOnline(false);
  const plain = makeTileAction({ method: 'POST', path: '/api/notes', label: 'Quick add' });
  const del = makeTileAction({ method: 'DELETE', path: '/api/notes/1', label: 'Remove' });
  const withSchema = makeTileAction({
    method: 'POST',
    path: '/api/notes',
    label: 'Schema add',
    body_schema: { type: 'object', properties: { body: { type: 'string' } } },
  });

  const { unmount: unmountPlain } = await renderTile(
    <TileActionButton action={plain} tileKey="demo.tile" />,
  );
  const plainButton = screen.getByRole('button', { name: /quick add/i });
  expect(plainButton).toBeDisabled();
  expect(plainButton).toHaveAttribute('title', "You're offline.");
  unmountPlain();

  const { unmount: unmountDelete } = await renderTile(
    <TileActionButton action={del} tileKey="demo.tile" />,
  );
  const deleteButton = screen.getByRole('button', { name: /^remove$/i });
  expect(deleteButton).toBeDisabled();
  expect(deleteButton).toHaveAttribute('title', "You're offline.");
  unmountDelete();

  await renderTile(<TileActionButton action={withSchema} tileKey="demo.tile" />);
  const schemaButton = screen.getByRole('button', { name: /^schema add$/i });
  expect(schemaButton).toBeDisabled();
  expect(schemaButton).toHaveAttribute('title', "You're offline.");
});
