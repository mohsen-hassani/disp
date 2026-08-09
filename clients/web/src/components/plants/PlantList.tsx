import { useInfiniteQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { AlertCircle, SearchX, Sprout } from 'lucide-react';
import { type ReactElement, useEffect, useRef, useState } from 'react';

import { plantsListInfiniteQueryOptions } from '../../api/queries';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { useOfflineState } from '../../hooks/useOfflineState';
import { EmptyState } from '../feedback/EmptyState';
import { SavedDataLabel } from '../feedback/SavedDataLabel';
import { PlantCard } from './PlantCard';

interface PlantListProps {
  q: string | undefined;
  onQChange: (q: string | undefined) => void;
}

// PlantCreate/name mirrors the backend's own bound, matching the search box's own reasonable cap.
const SEARCH_MAX_LENGTH = 200;

const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

function SkeletonRow(): ReactElement {
  return (
    <div
      aria-hidden="true"
      className="border-border bg-surface flex items-center gap-3 rounded-md border p-3"
    >
      <div className="bg-surface-sunken h-12 w-12 shrink-0 rounded-md" />
      <div className="flex flex-1 flex-col gap-2">
        <div className="bg-surface-sunken h-4 w-1/3 rounded-sm" />
        <div className="bg-surface-sunken h-4 w-1/4 rounded-full" />
      </div>
    </div>
  );
}

/** M14 §5's `/plants` list: toolbar, `useInfiniteQuery`, and the same four required states as `NoteList`. */
export function PlantList({ q, onQChange }: PlantListProps): ReactElement {
  const isOffline = useOfflineState();
  const [inputValue, setInputValue] = useState(q ?? '');
  const lastDispatchedRef = useRef(q ?? '');
  const debouncedInput = useDebouncedValue(inputValue, 300);

  useEffect(() => {
    if (debouncedInput !== lastDispatchedRef.current) {
      lastDispatchedRef.current = debouncedInput;
      onQChange(debouncedInput || undefined);
    }
  }, [debouncedInput, onQChange]);

  useEffect(() => {
    const incoming = q ?? '';
    if (incoming !== lastDispatchedRef.current) {
      lastDispatchedRef.current = incoming;
      setInputValue(incoming);
    }
  }, [q]);

  const filters = { q };
  const plantsQuery = useInfiniteQuery(plantsListInfiniteQueryOptions(filters));
  const filtersActive = Boolean(q);
  const items = plantsQuery.data?.pages.flatMap((page) => page.items) ?? [];

  function clearFilters(): void {
    setInputValue('');
    lastDispatchedRef.current = '';
    onQChange(undefined);
  }

  return (
    <>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <input
          id="plants-search"
          type="search"
          role="searchbox"
          value={inputValue}
          onChange={(event) => setInputValue(event.target.value)}
          placeholder="Search plants…"
          aria-label="Search plants"
          maxLength={SEARCH_MAX_LENGTH}
          className="border-border bg-surface min-w-0 flex-1 rounded-sm border px-3 py-2 text-sm sm:max-w-xs"
        />
        <div className="flex shrink-0 items-center gap-2">
          <Link to="/plants/calendar" className={secondaryButtonClass}>
            Calendar
          </Link>
          <Link to="/plants/new" className={primaryButtonClass}>
            Add plant
          </Link>
        </div>
      </div>

      <SavedDataLabel show={isOffline && plantsQuery.isSuccess} />

      {plantsQuery.isPending && (
        <div aria-busy="true" className="flex flex-col gap-3">
          <span className="sr-only">Loading plants…</span>
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      )}

      {plantsQuery.isError && (
        <div className="border-border bg-surface flex flex-col items-center gap-3 rounded-md border border-dashed p-8 text-center">
          <AlertCircle className="text-danger h-8 w-8" aria-hidden="true" />
          <p role="alert" className="text-text-muted text-sm">
            Failed to load plants.
          </p>
          <button
            type="button"
            onClick={() => void plantsQuery.refetch()}
            className={secondaryButtonClass}
          >
            Retry
          </button>
        </div>
      )}

      {plantsQuery.isSuccess && items.length === 0 && !filtersActive && (
        <EmptyState
          icon={Sprout}
          title="No plants yet. Add your first one to start tracking care."
          action={
            <Link to="/plants/new" className={primaryButtonClass}>
              Add your first plant
            </Link>
          }
        />
      )}

      {plantsQuery.isSuccess && items.length === 0 && filtersActive && (
        <EmptyState
          icon={SearchX}
          title="No plants match your search."
          action={
            <button type="button" onClick={clearFilters} className={secondaryButtonClass}>
              Clear filters
            </button>
          }
        />
      )}

      {items.length > 0 && (
        <ul className="flex flex-col gap-3">
          {items.map((plant) => (
            <li key={plant.id}>
              <PlantCard plant={plant} />
            </li>
          ))}
        </ul>
      )}

      {plantsQuery.hasNextPage && (
        <button
          type="button"
          onClick={() => void plantsQuery.fetchNextPage()}
          disabled={plantsQuery.isFetchingNextPage}
          className={`${secondaryButtonClass} mt-4 self-center`}
        >
          {plantsQuery.isFetchingNextPage ? 'Loading…' : 'Load more'}
        </button>
      )}
    </>
  );
}
