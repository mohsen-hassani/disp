import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { type ReactElement, useId } from 'react';

import { dashboardTile } from '../../api/generated';
import type { TileData, TileSpec } from '../../api/generated';
import { qk } from '../../api/queryKeys';
import { useIntervalRefresh } from '../../hooks/useIntervalRefresh';
import { useNavigableDomains } from '../../hooks/useNavigableDomains';
import { dateTime, relativeTime } from '../../lib/format';
import { ErrorBoundary } from '../feedback/ErrorBoundary';
import { TileActionButton } from './TileActionButton';
import { tileButtonClass } from './tileButton';
import { TileError } from './TileError';
import { TileItemRow } from './TileItemRow';
import { tileKeyDomain } from './tileLinks';
import { TileSkeleton } from './TileSkeleton';

const MAX_VISIBLE_ITEMS = 5;
const DEFAULT_REFRESH_SECONDS = 60;

interface TileCardProps {
  spec: TileSpec;
  initialData?: TileData;
}

function TileCardInner({ spec, initialData }: TileCardProps): ReactElement {
  const headingId = useId();
  const refreshMs = (spec.refresh_seconds ?? DEFAULT_REFRESH_SECONDS) * 1000;
  const navigable = useNavigableDomains();

  // §13.6: a manifest-declared button into the module's own screens. The
  // owning domain is the tile key's prefix, so this stays a generic rule —
  // and it renders only when that domain is actually reachable, so a module
  // whose screens this client predates gets no dead link.
  const navPath =
    spec.nav && navigable.has(tileKeyDomain(spec.key))
      ? `/${tileKeyDomain(spec.key)}${spec.nav.path ? `/${spec.nav.path}` : ''}`
      : null;

  // §13.4: seeded from the bulk `/tiles` payload so there's no loading
  // flash for a tile already in it; `refetchIntervalInBackground: false`
  // pauses ticking while hidden, and `useIntervalRefresh` below is the
  // "catch up immediately on resume" half TanStack Query doesn't do itself.
  const query = useQuery({
    queryKey: qk.dashboard.tile(spec.key),
    queryFn: async () => {
      const { data, error, response } = await dashboardTile({ path: { tile_key: spec.key } });
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load tile.');
      }
      return data;
    },
    initialData,
    refetchInterval: refreshMs,
    refetchIntervalInBackground: false,
    staleTime: refreshMs,
  });

  useIntervalRefresh({
    dataUpdatedAt: query.dataUpdatedAt,
    intervalMs: refreshMs,
    refetch: query.refetch,
  });

  if (query.isPending) {
    return <TileSkeleton title={spec.title} />;
  }
  if (query.isError) {
    return <TileError title={spec.title} onRetry={() => void query.refetch()} />;
  }

  const tile = query.data;
  const items = tile.items ?? [];
  const visibleItems = items.slice(0, MAX_VISIBLE_ITEMS);
  const extraCount = items.length - visibleItems.length;
  const actions = tile.actions ?? [];

  return (
    <article
      aria-labelledby={headingId}
      className="border-border bg-surface flex flex-col rounded-md border p-4"
    >
      <header className="mb-2 flex items-center justify-between gap-2">
        <h3 id={headingId} className="text-text truncate text-sm font-medium">
          {tile.title}
        </h3>
        <div className="flex shrink-0 items-center gap-2">
          {tile.count !== null && tile.count !== undefined && (
            <span className="bg-surface-sunken text-text-muted rounded-full px-2 py-0.5 text-xs">
              {tile.count}
            </span>
          )}
          {/* §13.3: relative timestamp, visible only on hover/focus — the
              sr-only text is always in the a11y tree regardless. A <button>
              (rather than a tabIndex-hacked <span>) so it's natively
              focusable and gets the browser's own title tooltip for free. */}
          <button
            type="button"
            title={dateTime(tile.generated_at)}
            className="text-text-muted cursor-default border-0 bg-transparent p-0 text-xs"
          >
            <span className="sr-only">Updated {relativeTime(tile.generated_at)}</span>
            <span
              aria-hidden="true"
              className="opacity-0 transition-opacity duration-fast hover:opacity-100 focus:opacity-100 motion-reduce:transition-none"
            >
              {relativeTime(tile.generated_at)}
            </span>
          </button>
        </div>
      </header>

      {visibleItems.length > 0 ? (
        <ul className="divide-border flex flex-col divide-y">
          {visibleItems.map((item) => (
            <TileItemRow key={item.id} item={item} />
          ))}
        </ul>
      ) : (
        <p className="text-text-muted text-sm italic">{tile.empty_text ?? 'Nothing here yet.'}</p>
      )}
      {extraCount > 0 && <p className="text-text-muted mt-1 text-xs">+{extraCount} more</p>}

      {(actions.length > 0 || navPath) && (
        <footer className="border-border mt-3 flex flex-wrap gap-2 border-t pt-3">
          {navPath && spec.nav && (
            <Link to={navPath} className={tileButtonClass}>
              {spec.nav.label}
            </Link>
          )}
          {actions.map((action) => (
            <TileActionButton key={action.id} action={action} tileKey={spec.key} />
          ))}
        </footer>
      )}
    </article>
  );
}

// §13.8: one failing tile's render must never affect its siblings. The
// query-level failure path above (`TileError`) handles a failed *request*;
// this boundary catches an unexpected render exception from anything
// beneath it.
export function TileCard(props: TileCardProps): ReactElement {
  return (
    <ErrorBoundary
      fallback={(_error, reset) => <TileError title={props.spec.title} onRetry={reset} />}
    >
      <TileCardInner {...props} />
    </ErrorBoundary>
  );
}
