import * as Dialog from '@radix-ui/react-dialog';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { MoreVertical } from 'lucide-react';
import { type ReactElement, useId, useRef, useState } from 'react';

import type { CareIntervalOut } from '../../api/generated';
import { useOfflineState } from '../../hooks/useOfflineState';
import { useToast } from '../feedback/ToastProvider';
import { CompleteDialog } from './CompleteDialog';
import { IntervalDueBadge } from './DueBadge';
import { IntervalFormDialog } from './IntervalFormDialog';
import { describePlantError, useDeleteInterval } from './usePlantMutations';

interface IntervalListProps {
  plantId: string;
  intervals: CareIntervalOut[];
}

const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const menuItemClass =
  'text-text hover:bg-surface-sunken focus-visible:bg-surface-sunken data-[highlighted]:bg-surface-sunken block w-full cursor-pointer rounded-sm px-3 py-1.5 text-left text-sm outline-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50';

interface IntervalRowProps {
  plantId: string;
  interval: CareIntervalOut;
  onComplete: (interval: CareIntervalOut) => void;
  onEdit: (interval: CareIntervalOut) => void;
}

function IntervalRow({ plantId, interval, onComplete, onEdit }: IntervalRowProps): ReactElement {
  const isOffline = useOfflineState();
  const { showToast } = useToast();
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const confirmTitleId = useId();
  const moreActionsRef = useRef<HTMLButtonElement>(null);
  const deleteMutation = useDeleteInterval();

  return (
    <li className="border-border bg-surface flex items-center justify-between gap-3 rounded-md border p-3">
      <div className="min-w-0 flex-1">
        <p className="text-text truncate text-sm font-medium">{interval.name}</p>
        <p className="text-text-muted text-xs">Every {interval.interval_days} days</p>
        <div className="mt-1">
          <IntervalDueBadge daysOverdue={interval.days_overdue} nextDueOn={interval.next_due_on} />
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <button
          type="button"
          onClick={() => onComplete(interval)}
          disabled={isOffline || !interval.active}
          title={isOffline ? "You're offline." : undefined}
          className={secondaryButtonClass}
        >
          Mark done
        </button>
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              ref={moreActionsRef}
              type="button"
              aria-label={`More actions for "${interval.name}"`}
              className="text-text-muted focus-visible:outline-accent flex h-11 w-11 items-center justify-center rounded-sm focus-visible:outline focus-visible:outline-2"
            >
              <MoreVertical className="h-4 w-4" aria-hidden="true" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              className="border-border bg-surface-raised shadow-overlay z-10 w-36 rounded-md border p-1"
            >
              <DropdownMenu.Item
                className={menuItemClass}
                disabled={isOffline}
                onSelect={() => onEdit(interval)}
              >
                Edit
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

      <Dialog.Root open={confirmDeleteOpen} onOpenChange={setConfirmDeleteOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/40" />
          <Dialog.Content
            aria-labelledby={confirmTitleId}
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              moreActionsRef.current?.focus();
            }}
            className="border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4"
          >
            <Dialog.Title id={confirmTitleId} className="text-text mb-2 text-sm font-medium">
              Delete &quot;{interval.name}&quot;?
            </Dialog.Title>
            <p className="text-text-muted mb-4 text-sm">This can&apos;t be undone.</p>
            <div className="flex justify-end gap-2">
              <Dialog.Close className={secondaryButtonClass}>Cancel</Dialog.Close>
              <button
                type="button"
                onClick={() => {
                  setConfirmDeleteOpen(false);
                  deleteMutation.mutate(
                    { plantId, intervalId: interval.id },
                    { onError: (error) => showToast(describePlantError(error), 'error') },
                  );
                }}
                disabled={deleteMutation.isPending}
                className="bg-danger text-accent-text rounded-sm px-3 py-1.5 text-sm font-medium disabled:opacity-60"
              >
                Delete interval
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </li>
  );
}

/** M14 §5's detail-screen interval list: add/edit/delete, and the "Mark done" action that opens `CompleteDialog`. */
export function IntervalList({ plantId, intervals }: IntervalListProps): ReactElement {
  const isOffline = useOfflineState();
  const [addOpen, setAddOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<CareIntervalOut | null>(null);
  const [completeTarget, setCompleteTarget] = useState<CareIntervalOut | null>(null);

  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-text text-sm font-medium">Care schedule</h2>
        <button
          type="button"
          onClick={() => setAddOpen(true)}
          disabled={isOffline}
          title={isOffline ? "You're offline." : undefined}
          className={primaryButtonClass}
        >
          Add interval
        </button>
      </div>

      {intervals.length === 0 ? (
        <p className="text-text-muted text-sm italic">No care intervals yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {intervals.map((interval) => (
            <IntervalRow
              key={interval.id}
              plantId={plantId}
              interval={interval}
              onComplete={setCompleteTarget}
              onEdit={setEditTarget}
            />
          ))}
        </ul>
      )}

      <IntervalFormDialog
        plantId={plantId}
        mode="add"
        interval={null}
        open={addOpen}
        onOpenChange={setAddOpen}
      />
      <IntervalFormDialog
        plantId={plantId}
        mode="edit"
        interval={editTarget}
        open={editTarget !== null}
        onOpenChange={(open) => !open && setEditTarget(null)}
      />
      <CompleteDialog
        plantId={plantId}
        interval={completeTarget}
        open={completeTarget !== null}
        onOpenChange={(open) => !open && setCompleteTarget(null)}
      />
    </section>
  );
}
