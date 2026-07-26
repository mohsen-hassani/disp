import * as Dialog from '@radix-ui/react-dialog';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { ArrowLeft, MoreVertical, Pin } from 'lucide-react';
import { type ReactElement, useEffect, useId, useState } from 'react';

import { noteDetailQueryOptions } from '../api/queries';
import { ShareDialog } from '../components/notes/ShareDialog';
import { NoteEditor } from '../components/notes/NoteEditor';
import {
  describeNoteError,
  useDeleteNote,
  useTogglePinned,
  useUpdateNote,
} from '../components/notes/useNoteMutations';
import { SavedDataLabel } from '../components/feedback/SavedDataLabel';
import { useToast } from '../components/feedback/ToastProvider';
import { useOfflineState } from '../hooks/useOfflineState';
import { setPageTitleOverride } from '../hooks/usePageTitle';
import { dateTime } from '../lib/format';

interface NoteDetailPageProps {
  noteId: string;
}

const iconButtonClass =
  'text-text-muted focus-visible:outline-accent rounded-sm p-1.5 focus-visible:outline focus-visible:outline-2';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const menuItemClass =
  'text-text hover:bg-surface-sunken focus-visible:bg-surface-sunken data-[highlighted]:bg-surface-sunken block w-full cursor-pointer rounded-sm px-3 py-1.5 text-left text-sm outline-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50';

// Router-ignored (leading `-`) — see -login.tsx's doc for why. `noteId`
// comes in as a prop (from `Route.useParams()` in the real route) rather
// than a generic `useParams({ strict: false })` read, so tests can mount
// this directly without constructing a param-matching test router.
export function NoteDetailPage({ noteId }: NoteDetailPageProps): ReactElement {
  const noteQuery = useQuery(noteDetailQueryOptions(noteId));
  const navigate = useNavigate();
  const { showToast } = useToast();
  const isOffline = useOfflineState();
  const [editing, setEditing] = useState(false);
  const [editError, setEditError] = useState<string | undefined>();
  const [shareOpen, setShareOpen] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const confirmDeleteTitleId = useId();

  const updateMutation = useUpdateNote(noteId);
  const pinMutation = useTogglePinned();
  const deleteMutation = useDeleteNote();

  const note = noteQuery.data;
  const heading = note ? note.title || 'Untitled' : '';

  useEffect(() => {
    if (!note) {
      return undefined;
    }
    setPageTitleOverride(`${note.title || 'Untitled'} · DISP`);
    return () => setPageTitleOverride(null);
  }, [note]);

  if (noteQuery.isPending) {
    return <p aria-busy="true">Loading…</p>;
  }
  if (noteQuery.isError || !note) {
    return <p role="alert">Failed to load the note.</p>;
  }

  function handleDelete(): void {
    deleteMutation.mutate(noteId, {
      onSuccess: () => {
        showToast('Note deleted.');
        void navigate({ to: '/notes' });
      },
      onError: (error) => showToast(describeNoteError(error), 'danger'),
    });
  }

  return (
    <>
      <button
        type="button"
        onClick={() => void navigate({ to: '/notes' })}
        className={`${secondaryButtonClass} mb-4 inline-flex items-center gap-1.5`}
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back
      </button>

      <div className="mb-1 flex items-start justify-between gap-3">
        <h1 className="min-w-0 break-words">{heading}</h1>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={() =>
              pinMutation.mutate(
                { id: noteId, pinned: !note.pinned },
                { onError: (error) => showToast(describeNoteError(error), 'danger') },
              )
            }
            disabled={pinMutation.isPending || isOffline}
            title={isOffline ? "You're offline." : undefined}
            aria-pressed={note.pinned}
            aria-label={note.pinned ? 'Unpin note' : 'Pin note'}
            className={`${iconButtonClass} disabled:opacity-60`}
          >
            <Pin
              className={note.pinned ? 'text-accent h-5 w-5 fill-current' : 'h-5 w-5'}
              aria-hidden="true"
            />
          </button>

          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button type="button" aria-label="More actions" className={iconButtonClass}>
                <MoreVertical className="h-5 w-5" aria-hidden="true" />
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
                  onSelect={() => setShareOpen(true)}
                >
                  Share
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
      </div>

      <p className="text-text-muted mb-4 text-xs">
        Created {dateTime(note.created_at)} · Updated {dateTime(note.updated_at)}
      </p>

      <SavedDataLabel show={isOffline} />

      {editing ? (
        <NoteEditor
          mode="edit"
          initialBody={note.body}
          submitting={updateMutation.isPending}
          error={editError}
          onSubmit={(values) => {
            setEditError(undefined);
            updateMutation.mutate(
              { body: values.body },
              {
                onSuccess: () => setEditing(false),
                onError: (error) => setEditError(describeNoteError(error)),
              },
            );
          }}
          onCancel={() => {
            setEditError(undefined);
            setEditing(false);
          }}
        />
      ) : (
        <>
          <button
            type="button"
            onClick={() => !isOffline && setEditing(true)}
            disabled={isOffline}
            title={isOffline ? "You're offline." : undefined}
            className="focus-visible:outline-accent block w-full rounded-sm text-left whitespace-pre-wrap break-words text-sm focus-visible:outline focus-visible:outline-2 disabled:cursor-default"
          >
            {note.body}
          </button>
          <button
            type="button"
            onClick={() => setEditing(true)}
            disabled={isOffline}
            title={isOffline ? "You're offline." : undefined}
            className={`${secondaryButtonClass} mt-4`}
          >
            Edit
          </button>
        </>
      )}

      <ShareDialog
        noteId={noteId}
        noteHeading={heading}
        open={shareOpen}
        onOpenChange={setShareOpen}
      />

      <Dialog.Root open={confirmDeleteOpen} onOpenChange={setConfirmDeleteOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/40" />
          <Dialog.Content
            aria-labelledby={confirmDeleteTitleId}
            className="border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4"
          >
            <Dialog.Title id={confirmDeleteTitleId} className="text-text mb-2 text-sm font-medium">
              Delete &quot;{heading}&quot;?
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
                Delete
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
