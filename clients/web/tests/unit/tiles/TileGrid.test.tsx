import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

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
