import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from '@tanstack/react-router';
import { CalendarDays, Leaf, Plus } from 'lucide-react';
import { type ReactElement, useEffect, useState } from 'react';

import { plantsDueQueryOptions, plantsListInfiniteQueryOptions } from '../api/queries';
import { EmptyState } from '../components/feedback/EmptyState';
import { Spinner } from '../components/feedback/Spinner';
import { CreatePlantDialog } from '../components/plants/CreatePlantDialog';
import { PlantCard } from '../components/plants/PlantCard';
import { primaryButtonClass, secondaryButtonClass } from '../components/plants/styles';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { currentMonth } from '../lib/calendar';
import { useOnlineStatus } from '../hooks/useOnlineStatus';

interface PlantsListPageProps {
  q?: string;
  onQChange: (q: string | undefined) => void;
}

export function PlantsListPage({ q, onQChange }: PlantsListPageProps): ReactElement {
  const navigate = useNavigate();
  const online = useOnlineStatus();
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState(q ?? '');
  const debounced = useDebouncedValue(search, 300);

  useEffect(() => {
    onQChange(debounced || undefined);
  }, [debounced]);

  const dueQuery = useQuery(plantsDueQueryOptions());
  const listQuery = useInfiniteQuery(plantsListInfiniteQueryOptions({ q: q || undefined }));

  const plants = listQuery.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-text text-xl font-semibold">Plants</h1>
        <div className="flex items-center gap-2">
          {/* `month` is required by the route's validateSearch, so it is
              passed explicitly rather than relying on a fallback. */}
          <Link
            to="/plants/calendar"
            search={{ month: currentMonth() }}
            className={`${secondaryButtonClass} inline-flex items-center gap-1.5`}
          >
            <CalendarDays className="h-4 w-4" aria-hidden="true" />
            Calendar
          </Link>
          <button
            type="button"
            className={`${primaryButtonClass} inline-flex items-center gap-1.5`}
            disabled={!online}
            onClick={() => setCreateOpen(true)}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            New plant
          </button>
        </div>
      </header>

      {/* The same derived due state the dashboard tile renders, stated as a
          sentence so "you are N days behind" is the first thing on screen. */}
      {dueQuery.data && dueQuery.data.count > 0 ? (
        <p
          className={`rounded-md px-3 py-2 text-sm ${
            dueQuery.data.overdue_count > 0
              ? 'bg-danger text-accent-text'
              : 'bg-surface-sunken text-text'
          }`}
        >
          {dueQuery.data.summary}
        </p>
      ) : null}

      <input
        type="search"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search plants"
        aria-label="Search plants"
        className="border-border bg-surface text-text focus-visible:outline-accent w-full rounded-sm border px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
      />

      {listQuery.isPending ? (
        <ul aria-busy="true" className="flex flex-col gap-2">
          {[0, 1, 2].map((index) => (
            <li
              key={index}
              className="border-border bg-surface h-20 animate-pulse rounded-md border"
            />
          ))}
        </ul>
      ) : listQuery.isError ? (
        <div className="border-border rounded-md border p-4">
          <p className="text-text mb-3 text-sm">Could not load your plants.</p>
          <button
            type="button"
            className={secondaryButtonClass}
            onClick={() => void listQuery.refetch()}
          >
            Retry
          </button>
        </div>
      ) : plants.length === 0 ? (
        <EmptyState
          icon={Leaf}
          title={q ? `No plants match “${q}”` : 'No plants yet'}
          action={
            q ? undefined : (
              <button
                type="button"
                className={primaryButtonClass}
                onClick={() => setCreateOpen(true)}
              >
                Add your first plant
              </button>
            )
          }
        />
      ) : (
        <>
          <ul className="flex flex-col gap-2">
            {plants.map((plant) => (
              <li key={plant.id}>
                <PlantCard plant={plant} />
              </li>
            ))}
          </ul>

          {listQuery.hasNextPage ? (
            <button
              type="button"
              className={`${secondaryButtonClass} inline-flex items-center gap-2 self-start`}
              disabled={listQuery.isFetchingNextPage}
              onClick={() => void listQuery.fetchNextPage()}
            >
              {listQuery.isFetchingNextPage ? <Spinner /> : null}
              Load more
            </button>
          ) : null}
        </>
      )}

      <CreatePlantDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(plantId) => void navigate({ to: '/plants/$plantId', params: { plantId } })}
      />
    </div>
  );
}
