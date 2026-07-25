import { describe, expect, it } from 'vitest';

import type { TileSpec } from '../../../src/api/generated';
import {
  actionDomainQueryKey,
  sortTileSpecs,
  translateTileHref,
} from '../../../src/components/tiles/tileLinks';
import { makeTileSpec } from './fixtures';

// Test 26.
describe('translateTileHref', () => {
  it('maps an /api/ path for a module with a registered screen to its UI route', () => {
    expect(translateTileHref('/api/notes/abc')).toBe('/notes/abc');
  });

  it('returns null for a module with no registered screen', () => {
    expect(translateTileHref('/api/unregistered-module/abc')).toBeNull();
  });

  it('returns null for a href that is not an /api/ path', () => {
    expect(translateTileHref('/notes/abc')).toBeNull();
    expect(translateTileHref('https://evil.example/notes/abc')).toBeNull();
  });
});

describe('actionDomainQueryKey', () => {
  it('derives the first path segment after /api/', () => {
    expect(actionDomainQueryKey('/api/notes')).toEqual(['notes']);
    expect(actionDomainQueryKey('/api/notes/123')).toEqual(['notes']);
  });

  it('returns an empty array when there is no segment to derive', () => {
    expect(actionDomainQueryKey('/api/')).toEqual([]);
  });
});

// Test 15.
describe('sortTileSpecs', () => {
  it('orders by order ascending, then key ascending', () => {
    const specs: TileSpec[] = [
      makeTileSpec({ key: 'b.tile', order: 1 }),
      makeTileSpec({ key: 'a.tile', order: 0 }),
      makeTileSpec({ key: 'c.tile', order: 1 }),
    ];
    expect(sortTileSpecs(specs).map((s) => s.key)).toEqual(['a.tile', 'b.tile', 'c.tile']);
  });

  it('does not mutate the input array', () => {
    const specs = [
      makeTileSpec({ key: 'b.tile', order: 1 }),
      makeTileSpec({ key: 'a.tile', order: 0 }),
    ];
    const original = [...specs];
    sortTileSpecs(specs);
    expect(specs).toEqual(original);
  });
});
