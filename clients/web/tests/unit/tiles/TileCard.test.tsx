import { screen, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { TileCard } from '../../../src/components/tiles/TileCard';
import { makeTileAction, makeTileData, makeTileItem, makeTileSpec } from './fixtures';
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

// Test 17.
it('renders count: 0 as "0", not nothing', async () => {
  const spec = makeTileSpec();
  await renderTile(
    <TileCard spec={spec} initialData={makeTileData({ key: spec.key, count: 0 })} />,
  );
  expect(screen.getByText('0')).toBeInTheDocument();
});

// Test 18.
it('renders empty_text in muted italic when items is empty, and still renders actions', async () => {
  const spec = makeTileSpec();
  await renderTile(
    <TileCard
      spec={spec}
      initialData={makeTileData({
        key: spec.key,
        items: [],
        empty_text: 'Nothing to show',
        actions: [makeTileAction()],
      })}
    />,
  );
  expect(screen.getByText('Nothing to show')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /do it/i })).toBeInTheDocument();
});

// Test 19.
it('renders at most five items plus a "+N more" line', async () => {
  const spec = makeTileSpec();
  const items = Array.from({ length: 7 }, (_, index) =>
    makeTileItem({ id: `item-${index}`, primary: `Item ${index}` }),
  );
  await renderTile(<TileCard spec={spec} initialData={makeTileData({ key: spec.key, items })} />);
  expect(screen.getAllByRole('listitem')).toHaveLength(5);
  expect(screen.getByText('+2 more')).toBeInTheDocument();
});

// Test 24 (this tile's slice of it): a failed request renders TileError
// with a working Retry, scoped to this one card.
it('renders TileError with a working Retry when the request fails', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        type: 'about:blank',
        title: 'Server error',
        status: 500,
        detail: 'boom',
        instance: '/api/dashboard/tiles/demo.tile',
        code: 'internal_error',
        request_id: 'req-1',
      }),
      { status: 500, headers: { 'Content-Type': 'application/json' } },
    ),
  );
  const spec = makeTileSpec();
  await renderTile(<TileCard spec={spec} />);

  await waitFor(() => expect(screen.getByText(/couldn't be loaded/i)).toBeInTheDocument());
  expect(screen.getByRole('heading', { name: spec.title })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
});

// §13.6's manifest-declared nav button. `renderTile` seeds the manifest that
// makes a domain reachable, so these two cases differ only in the tile key's
// domain — no component-level knowledge of any particular module.
it('renders a manifest-declared nav button linking into the module screens', async () => {
  const spec = makeTileSpec({ key: 'notes.latest', nav: { label: 'All notes', path: '' } });
  await renderTile(<TileCard spec={spec} initialData={makeTileData({ key: spec.key })} />);

  expect(screen.getByRole('link', { name: 'All notes' })).toHaveAttribute('href', '/notes');
});

it('joins a nav sub-path under the module namespace', async () => {
  const spec = makeTileSpec({ key: 'notes.latest', nav: { label: 'New', path: 'new' } });
  await renderTile(<TileCard spec={spec} initialData={makeTileData({ key: spec.key })} />);

  expect(screen.getByRole('link', { name: 'New' })).toHaveAttribute('href', '/notes/new');
});

it('omits the nav button for a module this client has no screens for', async () => {
  // The tile still renders — only the link to nowhere is suppressed.
  const spec = makeTileSpec({ nav: { label: 'Manage', path: '' } });
  await renderTile(<TileCard spec={spec} initialData={makeTileData({ key: spec.key })} />);

  expect(screen.queryByRole('link', { name: 'Manage' })).not.toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Demo' })).toBeInTheDocument();
});

it('renders the footer for a nav button even when the tile has no actions', async () => {
  const spec = makeTileSpec({ key: 'notes.latest', nav: { label: 'All notes', path: '' } });
  await renderTile(
    <TileCard spec={spec} initialData={makeTileData({ key: spec.key, actions: [] })} />,
  );

  expect(screen.getByRole('link', { name: 'All notes' })).toBeInTheDocument();
});
