import * as Switch from '@radix-ui/react-switch';
import { useInfiniteQuery } from '@tanstack/react-query';
import { AlertCircle, SearchX, StickyNote } from 'lucide-react';
import { type ReactElement, useEffect, useRef, useState } from 'react';

import type { NoteOut } from '../../api/generated';
import { notesListInfiniteQueryOptions } from '../../api/queries';
import { qk } from '../../api/queryKeys';
import { EmptyState } from '../feedback/EmptyState';
import { SavedDataLabel } from '../feedback/SavedDataLabel';
import { useToast } from '../feedback/ToastProvider';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { useOfflineState } from '../../hooks/useOfflineState';
import { NoteCard } from './NoteCard';
import { ShareDialog } from './ShareDialog';
import { describeNoteError, useDeleteNote, useTogglePinned } from './useNoteMutations';

interface NoteListProps {
  q: string | undefined;
  pinned: boolean | undefined;
  onQChange: (q: string | undefined) => void;
  onPinnedChange: (pinned: boolean | undefined) => void;
  onNewNote: () => void;
}

// WEB-SPEC §19.2: search `q` ≤200.
const SEARCH_MAX_LENGTH = 200;

const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

function SkeletonRow(): ReactElement {
  return (
    <div
      aria-hidden="true"
      className="border-border bg-surface flex flex-col gap-2 rounded-md border p-3"
    >
      <div className="bg-surface-sunken h-4 w-1/3 rounded-sm" />
      <div className="bg-surface-sunken h-3 w-full rounded-sm" />
      <div className="bg-surface-sunken h-3 w-2/3 rounded-sm" />
    </div>
  );
}

/** §16.1's `/notes` list: toolbar, `useInfiniteQuery`, and the four required states. */
export function NoteList({
  q,
  pinned,
  onQChange,
  onPinnedChange,
  onNewNote,
}: NoteListProps): ReactElement {
  const { showToast } = useToast();
  const isOffline = useOfflineState();
  const [inputValue, setInputValue] = useState(q ?? '');
  const lastDispatchedRef = useRef(q ?? '');
  const debouncedInput = useDebouncedValue(inputValue, 300);
  const [shareTarget, setShareTarget] = useState<NoteOut | null>(null);

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

  const filters = { q, pinned };
  const listKey = qk.notes.list(filters);
  const notesQuery = useInfiniteQuery(notesListInfiniteQueryOptions(filters));
  const pinMutation = useTogglePinned(listKey);
  const deleteMutation = useDeleteNote(listKey);

  const pinPendingId = pinMutation.isPending ? pinMutation.variables?.id : undefined;
  const filtersActive = Boolean(q) || pinned === true;
  const items = notesQuery.data?.pages.flatMap((page) => page.items) ?? [];

  function clearFilters(): void {
    setInputValue('');
    lastDispatchedRef.current = '';
    onQChange(undefined);
    onPinnedChange(undefined);
  }

  return (
    <>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 flex-wrap items-center gap-3">
          <input
            id="notes-search"
            type="search"
            role="searchbox"
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
            placeholder="Search notes…"
            aria-label="Search notes"
            maxLength={SEARCH_MAX_LENGTH}
            className="border-border bg-surface min-w-0 flex-1 rounded-sm border px-3 py-2 text-sm sm:max-w-xs"
          />
          <div className="flex items-center gap-2 text-sm">
            <Switch.Root
              id="notes-pinned-only"
              checked={pinned === true}
              onCheckedChange={(checked) => onPinnedChange(checked || undefined)}
              className="bg-surface-sunken data-[state=checked]:bg-accent focus-visible:outline-accent relative h-6 w-10 rounded-full transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              <Switch.Thumb className="bg-surface block h-5 w-5 translate-x-0.5 rounded-full transition-transform data-[state=checked]:translate-x-[18px]" />
            </Switch.Root>
            <label htmlFor="notes-pinned-only">Pinned only</label>
          </div>
        </div>
        <button
          type="button"
          onClick={onNewNote}
          disabled={isOffline}
          title={isOffline ? "You're offline." : undefined}
          className={primaryButtonClass}
        >
          New note
        </button>
      </div>

      <SavedDataLabel show={isOffline && notesQuery.isSuccess} />

      {notesQuery.isPending && (
        <div aria-busy="true" className="flex flex-col gap-3">
          <span className="sr-only">Loading notes…</span>
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      )}

      {notesQuery.isError && (
        <div className="border-border bg-surface flex flex-col items-center gap-3 rounded-md border border-dashed p-8 text-center">
          <AlertCircle className="text-danger h-8 w-8" aria-hidden="true" />
          <p role="alert" className="text-text-muted text-sm">
            Failed to load notes.
          </p>
          <button
            type="button"
            onClick={() => void notesQuery.refetch()}
            className={secondaryButtonClass}
          >
            Retry
          </button>
        </div>
      )}

      {notesQuery.isSuccess && items.length === 0 && !filtersActive && (
        <EmptyState
          icon={StickyNote}
          title="No notes yet. Your first one is a click away."
          action={
            <button
              type="button"
              onClick={onNewNote}
              disabled={isOffline}
              title={isOffline ? "You're offline." : undefined}
              className={primaryButtonClass}
            >
              Create your first note
            </button>
          }
        />
      )}

      {notesQuery.isSuccess && items.length === 0 && filtersActive && (
        <EmptyState
          icon={SearchX}
          title="No notes match your search."
          action={
            <button type="button" onClick={clearFilters} className={secondaryButtonClass}>
              Clear filters
            </button>
          }
        />
      )}

      {items.length > 0 && (
        <ul className="flex flex-col gap-3">
          {items.map((note) => (
            <li key={note.id}>
              <NoteCard
                note={note}
                pinPending={pinPendingId === note.id}
                offline={isOffline}
                onTogglePinned={(target) =>
                  pinMutation.mutate(
                    { id: target.id, pinned: !target.pinned },
                    {
                      onError: (error) => showToast(describeNoteError(error), 'error'),
                    },
                  )
                }
                onShare={setShareTarget}
                onDelete={(target) =>
                  deleteMutation.mutate(target.id, {
                    onError: (error) => showToast(describeNoteError(error), 'error'),
                  })
                }
              />
            </li>
          ))}
        </ul>
      )}

      {notesQuery.hasNextPage && (
        <button
          type="button"
          onClick={() => void notesQuery.fetchNextPage()}
          disabled={notesQuery.isFetchingNextPage}
          className={`${secondaryButtonClass} mt-4 self-center`}
        >
          {notesQuery.isFetchingNextPage ? 'Loading…' : 'Load more'}
        </button>
      )}

      <ShareDialog
        noteId={shareTarget?.id ?? null}
        noteHeading={shareTarget ? shareTarget.title || 'this note' : ''}
        open={shareTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setShareTarget(null);
          }
        }}
      />
    </>
  );
}
