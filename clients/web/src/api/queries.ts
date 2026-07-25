import { queryOptions } from '@tanstack/react-query';

import { dashboardManifest, dashboardTiles } from './generated';
import type { DashboardManifestResponse } from './generated';
import { qk } from './queryKeys';

/**
 * The dashboard manifest is needed today by the app shell's nav (§12.2) and
 * by `_app`'s route loader (so `/settings/:domain` can validate a domain
 * without a network call, per §9) — well before M05 (the dashboard screen)
 * exists to "own" it. M05 should extend this file for the tiles/settings
 * queries it needs rather than duplicating a second manifest query
 * elsewhere; the query key and shape here are already the canonical ones.
 */
export function dashboardManifestQueryOptions() {
  return queryOptions({
    queryKey: qk.dashboard.manifest(),
    queryFn: async () => {
      const { data, error, response } = await dashboardManifest();
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load the dashboard manifest.');
      }
      return data;
    },
    // WEB-SPEC §10.2: ['dashboard','manifest'] — 10 min staleTime, no refetch on focus.
    staleTime: 10 * 60_000,
    refetchOnWindowFocus: false,
  });
}

/**
 * WEB-SPEC §9: `/settings/:domain` validates `domain` against modules that
 * actually have a settings panel — not just any module in the manifest —
 * without a network call. `routes/_app.settings.$domain.tsx` is the caller;
 * pulled out as a pure function so that route's `beforeLoad` and a future
 * `SettingsIndex` (M06, listing the same panels) share one definition of
 * "valid domain" rather than each re-deriving it from the manifest shape.
 */
export function settingsPanelDomains(manifest: DashboardManifestResponse): string[] {
  return manifest.modules
    .filter((module) => module.settings_panels.length > 0)
    .map((module) => module.domain);
}

/** §13.1's bulk fetch — one `TileData` per tile, on first render. */
export function dashboardTilesQueryOptions() {
  return queryOptions({
    queryKey: qk.dashboard.tiles(),
    queryFn: async () => {
      const { data, error, response } = await dashboardTiles();
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load dashboard tiles.');
      }
      return data;
    },
    // WEB-SPEC §10.2: ['dashboard','tiles'] — always stale, refetch on focus.
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
}
