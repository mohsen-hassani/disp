import * as Dialog from '@radix-ui/react-dialog';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from '@tanstack/react-router';
import { ArrowLeft, MoreVertical } from 'lucide-react';
import { type ReactElement, useEffect, useId, useRef, useState } from 'react';

import { plantDetailQueryOptions } from '../api/queries';
import { useToast } from '../components/feedback/ToastProvider';
import { PlantDueBadge } from '../components/plants/DueBadge';
import { HistoryList } from '../components/plants/HistoryList';
import { IntervalList } from '../components/plants/IntervalList';
import { PhotoUpload } from '../components/plants/PhotoUpload';
import { describePlantError, useDeletePlant } from '../components/plants/usePlantMutations';
import { useOfflineState } from '../hooks/useOfflineState';
import { setPageTitleOverride } from '../hooks/usePageTitle';

interface PlantDetailPageProps {
  plantId: string;
}

const iconButtonClass =
  'text-text-muted focus-visible:outline-accent flex h-11 w-11 items-center justify-center rounded-sm focus-visible:outline focus-visible:outline-2';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const menuItemClass =
  'text-text hover:bg-surface-sunken focus-visible:bg-surface-sunken data-[highlighted]:bg-surface-sunken block w-full cursor-pointer rounded-sm px-3 py-1.5 text-left text-sm outline-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50';

// Router-ignored (leading `-`) — see `-login.tsx`'s doc for why. `plantId`
// comes in as a prop rather than a generic `useParams({ strict: false })`
// read, so this mounts directly in tests without a param-matching router.
export function PlantDetailPage({ plantId }: PlantDetailPageProps): ReactElement {
  const plantQuery = useQuery(plantDetailQueryOptions(plantId));
  const navigate = useNavigate();
  const { showToast } = useToast();
  const isOffline = useOfflineState();
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const confirmDeleteTitleId = useId();
  // §21 A11-equivalent: the confirm dialog opens from a dropdown item that's
  // already unmounted by the time it needs somewhere to return focus to.
  const moreActionsRef = useRef<HTMLButtonElement>(null);
  const deleteMutation = useDeletePlant();

  const plant = plantQuery.data;

  useEffect(() => {
    if (!plant) {
      return undefined;
    }
    setPageTitleOverride(`${plant.name} · DISP`);
    return () => setPageTitleOverride(null);
  }, [plant]);

  if (plantQuery.isPending) {
    return <p aria-busy="true">Loading…</p>;
  }
  if (plantQuery.isError || !plant) {
    return <p role="alert">Failed to load the plant.</p>;
  }

  function handleDelete(): void {
    deleteMutation.mutate(plantId, {
      onSuccess: () => {
        showToast('Plant deleted.', 'success');
        void navigate({ to: '/plants' });
      },
      onError: (error) => showToast(describePlantError(error), 'error'),
    });
  }

  return (
    <>
      <button
        type="button"
        onClick={() => void navigate({ to: '/plants' })}
        className={`${secondaryButtonClass} mb-4 inline-flex items-center gap-1.5`}
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back
      </button>

      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <PhotoUpload plant={plant} />
          <div className="min-w-0">
            <h1 className="min-w-0 break-words">{plant.name}</h1>
            <div className="mt-1">
              <PlantDueBadge
                dueCount={plant.due_count}
                maxDaysOverdue={plant.max_days_overdue}
                nextDueOn={plant.next_due_on}
              />
            </div>
          </div>
        </div>

        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              ref={moreActionsRef}
              type="button"
              aria-label="More actions"
              className={iconButtonClass}
            >
              <MoreVertical className="h-5 w-5" aria-hidden="true" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              className="border-border bg-surface-raised shadow-overlay z-10 w-36 rounded-md border p-1"
            >
              <DropdownMenu.Item asChild>
                <Link to="/plants/$plantId/edit" params={{ plantId }} className={menuItemClass}>
                  Edit
                </Link>
              </DropdownMenu.Item>
              <DropdownMenu.Item
                className={menuItemClass}
                disabled={isOffline}
                onSelect={() => setConfirmDeleteOpen(true)}
              >
                Delete
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>

      {plant.description && (
        <p className="text-text mb-3 text-sm whitespace-pre-wrap">{plant.description}</p>
      )}
      {plant.care_notes && (
        <div className="mb-4">
          <h2 className="text-text mb-1 text-sm font-medium">Care notes</h2>
          <p className="text-text-muted text-sm whitespace-pre-wrap">{plant.care_notes}</p>
        </div>
      )}

      <div className="mb-6">
        <IntervalList plantId={plantId} intervals={plant.intervals} />
      </div>

      <HistoryList plantId={plantId} />

      <Dialog.Root open={confirmDeleteOpen} onOpenChange={setConfirmDeleteOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/40" />
          <Dialog.Content
            aria-labelledby={confirmDeleteTitleId}
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              moreActionsRef.current?.focus();
            }}
            className="border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4"
          >
            <Dialog.Title id={confirmDeleteTitleId} className="text-text mb-2 text-sm font-medium">
              Delete &quot;{plant.name}&quot;?
            </Dialog.Title>
            <p className="text-text-muted mb-4 text-sm">This can&apos;t be undone.</p>
            <div className="flex justify-end gap-2">
              <Dialog.Close className={secondaryButtonClass}>Cancel</Dialog.Close>
              <button
                type="button"
                onClick={() => {
                  setConfirmDeleteOpen(false);
                  handleDelete();
                }}
                disabled={deleteMutation.isPending}
                className="bg-danger text-accent-text rounded-sm px-3 py-1.5 text-sm font-medium disabled:opacity-60"
              >
                Delete plant
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
