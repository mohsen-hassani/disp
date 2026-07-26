import { useQuery } from '@tanstack/react-query';
import { createFileRoute } from '@tanstack/react-router';
import { LayoutDashboard } from 'lucide-react';
import { type ReactElement, useMemo } from 'react';

import { dashboardManifestQueryOptions, dashboardTilesQueryOptions } from '../api/queries';
import { EmptyState } from '../components/feedback/EmptyState';
import { SavedDataLabel } from '../components/feedback/SavedDataLabel';
import { sortTileSpecs } from '../components/tiles/tileLinks';
import { TileGrid } from '../components/tiles/TileGrid';
import { useOfflineState } from '../hooks/useOfflineState';
import { InstallPromptCard } from '../pwa/InstallPromptCard';
import type { TileData } from '../api/generated';

export const Route = createFileRoute('/_app/')({
  component: DashboardPage,
  staticData: { title: 'Dashboard · DISP' },
});

function DashboardPage(): ReactElement {
  // `_app.tsx`'s loader already resolved the manifest; SideNav/BottomNav
  // read the same cache entry, so this is a second subscription, not a
  // second fetch.
  const manifestQuery = useQuery(dashboardManifestQueryOptions());
  const tilesQuery = useQuery(dashboardTilesQueryOptions());
  const isOffline = useOfflineState();

  const specs = useMemo(() => {
    const modules = manifestQuery.data?.modules ?? [];
    return sortTileSpecs(modules.flatMap((module) => module.tiles));
  }, [manifestQuery.data]);

  if (specs.length === 0) {
    return (
      <>
        <h1>Dashboard</h1>
        <InstallPromptCard />
        <EmptyState
          icon={LayoutDashboard}
          title="No tiles yet. Modules add tiles here once they're installed."
        />
      </>
    );
  }

  const tilesByKey: Record<string, TileData> | undefined = tilesQuery.data
    ? Object.fromEntries(tilesQuery.data.tiles.map((tile) => [tile.key, tile]))
    : undefined;

  return (
    <>
      <h1>Dashboard</h1>
      <InstallPromptCard />
      <SavedDataLabel show={isOffline && tilesQuery.isSuccess} />
      <TileGrid specs={specs} tilesByKey={tilesByKey} />
    </>
  );
}
