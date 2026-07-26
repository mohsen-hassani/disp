import { screen, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type { TileSize } from '../../../src/api/generated';
import { TileGrid } from '../../../src/components/tiles/TileGrid';
import { makeTileData, makeTileSpec } from './fixtures';
import { renderTile } from './testUtils';

// Test 16.
describe('TileGrid size fallback', () => {
  it('spans two columns at md+ for a large tile', async () => {
    const spec = makeTileSpec({ size: 'large' });
    await renderTile(
      <TileGrid specs={[spec]} tilesByKey={{ [spec.key]: makeTileData({ key: spec.key }) }} />,
    );
    expect(screen.getByRole('listitem').className).toContain('md:col-span-2');
  });

  it('falls back to a single column for an unknown size value, same as medium', async () => {
    const spec = makeTileSpec({ size: 'huge' as TileSize });
    await renderTile(
      <TileGrid specs={[spec]} tilesByKey={{ [spec.key]: makeTileData({ key: spec.key }) }} />,
    );
    expect(screen.getByRole('listitem').className).not.toContain('col-span');
  });

  it('renders skeletons, not tile cards, while the bulk fetch is pending', async () => {
    const spec = makeTileSpec();
    await renderTile(<TileGrid specs={[spec]} />);
    expect(screen.getByText(`Loading ${spec.title}…`)).toBeInTheDocument();
  });
});

describe('TileGrid error isolation (case 24)', () => {
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

  it('a failing tile renders TileError without affecting its sibling', async () => {
    const okSpec = makeTileSpec({ key: 'ok.tile', title: 'OK tile' });
    const failingSpec = makeTileSpec({ key: 'failing.tile', title: 'Failing tile' });

    fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes('failing.tile')) {
        return new Response(
          JSON.stringify({
            type: 'about:blank',
            title: 'Server error',
            status: 500,
            detail: 'boom',
            instance: '/api/dashboard/tiles/failing.tile',
            code: 'internal_error',
            request_id: 'req-iso',
          }),
          { status: 500, headers: { 'Content-Type': 'application/json' } },
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    await renderTile(
      <TileGrid
        specs={[okSpec, failingSpec]}
        tilesByKey={{ [okSpec.key]: makeTileData({ key: okSpec.key, title: okSpec.title }) }}
      />,
    );

    await waitFor(() => expect(screen.getByText(/couldn't be loaded/i)).toBeInTheDocument());
    expect(screen.getByRole('heading', { name: 'Failing tile' })).toBeInTheDocument();
    // The sibling tile still rendered its real content, not an error.
    expect(screen.getByRole('heading', { name: 'OK tile' })).toBeInTheDocument();
    expect(screen.queryAllByText(/couldn't be loaded/i)).toHaveLength(1);
  });
});
