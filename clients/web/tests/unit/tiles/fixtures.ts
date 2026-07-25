import type { TileAction, TileData, TileItem, TileSpec } from '../../../src/api/generated';

export function makeTileSpec(overrides: Partial<TileSpec> = {}): TileSpec {
  return {
    key: 'demo.tile',
    title: 'Demo',
    size: 'medium',
    refresh_seconds: 60,
    order: 0,
    ...overrides,
  };
}

export function makeTileItem(overrides: Partial<TileItem> = {}): TileItem {
  return { id: 'item-1', primary: 'Item one', ...overrides };
}

export function makeTileData(overrides: Partial<TileData> = {}): TileData {
  return { key: 'demo.tile', title: 'Demo', generated_at: new Date().toISOString(), ...overrides };
}

export function makeTileAction(overrides: Partial<TileAction> = {}): TileAction {
  return { id: 'action-1', label: 'Do it', method: 'POST', path: '/api/demo', ...overrides };
}
