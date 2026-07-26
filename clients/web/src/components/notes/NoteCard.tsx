import * as Dialog from '@radix-ui/react-dialog';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Link } from '@tanstack/react-router';
import { MoreVertical, Pin } from 'lucide-react';
import { type ReactElement, useId, useState } from 'react';

import type { NoteOut } from '../../api/generated';
import { relativeTime } from '../../lib/format';

interface NoteCardProps {
  note: NoteOut;
  pinPending: boolean;
  /** §18.5: disables the pin toggle and the menu's mutating items (not Open) while offline. */
  offline: boolean;
  onTogglePinned: (note: NoteOut) => void;
  onShare: (note: NoteOut) => void;
  onDelete: (note: NoteOut) => void;
}

const menuItemClass =
  'text-text hover:bg-surface-sunken focus-visible:bg-surface-sunken data-[highlighted]:bg-surface-sunken block w-full cursor-pointer rounded-sm px-3 py-1.5 text-left text-sm outline-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50';

/** §16.1's list row: pin indicator, title (or first line of body), a two-line preview, relative time, overflow menu. */
export function NoteCard({
  note,
  pinPending,
  offline,
  onTogglePinned,
  onShare,
  onDelete,
}: NoteCardProps): ReactElement {
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const confirmTitleId = useId();
  const firstLine = note.body.split('\n', 1)[0]?.trim();
  const heading = note.title || firstLine || 'Untitled';

  return (
    <article className="border-border bg-surface flex items-start gap-2 rounded-md border p-3">
      <button
        type="button"
        onClick={() => onTogglePinned(note)}
        disabled={pinPending || offline}
        title={offline ? "You're offline." : undefined}
        aria-pressed={note.pinned}
        aria-label={note.pinned ? 'Unpin note' : 'Pin note'}
        className="text-text-muted focus-visible:outline-accent mt-0.5 shrink-0 rounded-sm p-1 focus-visible:outline focus-visible:outline-2 disabled:opacity-60"
      >
        <Pin
          className={note.pinned ? 'text-accent h-4 w-4 fill-current' : 'h-4 w-4'}
          aria-hidden="true"
        />
      </button>

      <Link
        to="/notes/$noteId"
        params={{ noteId: note.id }}
        className="focus-visible:outline-accent min-w-0 flex-1 rounded-sm focus-visible:outline focus-visible:outline-2"
      >
        <p className="text-text truncate text-sm font-medium">{heading}</p>
        <p className="text-text-muted mt-0.5 line-clamp-2 text-sm break-words">{note.body}</p>
        <p className="text-text-muted mt-1 text-xs">{relativeTime(note.created_at)}</p>
      </Link>

      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            aria-label={`More actions for "${heading}"`}
            className="text-text-muted focus-visible:outline-accent shrink-0 rounded-sm p-1 focus-visible:outline focus-visible:outline-2"
          >
            <MoreVertical className="h-4 w-4" aria-hidden="true" />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            className="border-border bg-surface-raised shadow-overlay z-10 w-40 rounded-md border p-1"
          >
            <DropdownMenu.Item asChild>
              <Link to="/notes/$noteId" params={{ noteId: note.id }} className={menuItemClass}>
                Open
              </Link>
            </DropdownMenu.Item>
            <DropdownMenu.Item
              className={menuItemClass}
              disabled={offline}
              onSelect={() => onTogglePinned(note)}
            >
              {note.pinned ? 'Unpin' : 'Pin'}
            </DropdownMenu.Item>
            <DropdownMenu.Item
              className={menuItemClass}
              disabled={offline}
              onSelect={() => onShare(note)}
            >
              Share
            </DropdownMenu.Item>
            <DropdownMenu.Item
              className={menuItemClass}
              disabled={offline}
              onSelect={() => setConfirmDeleteOpen(true)}
            >
              Delete
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      <Dialog.Root open={confirmDeleteOpen} onOpenChange={setConfirmDeleteOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/40" />
          <Dialog.Content
            aria-labelledby={confirmTitleId}
            className="border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4"
          >
            <Dialog.Title id={confirmTitleId} className="text-text mb-2 text-sm font-medium">
              Delete &quot;{heading}&quot;?
            </Dialog.Title>
            <p className="text-text-muted mb-4 text-sm">This can&apos;t be undone.</p>
            <div className="flex justify-end gap-2">
              <Dialog.Close className="border-border text-text rounded-sm border px-3 py-1.5 text-sm">
                Cancel
              </Dialog.Close>
              <button
                type="button"
                onClick={() => {
                  setConfirmDeleteOpen(false);
                  onDelete(note);
                }}
                className="bg-danger text-accent-text rounded-sm px-3 py-1.5 text-sm font-medium"
              >
                Delete
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </article>
  );
}
