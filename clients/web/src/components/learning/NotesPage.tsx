import { useInfiniteQuery } from '@tanstack/react-query';
import { NotebookPen, Plus } from 'lucide-react';
import { type FormEvent, type ReactElement, useState } from 'react';

import type { DispModulesLearningSchemasNoteOut } from '../../api/generated';
import { learningNotesInfiniteQueryOptions } from '../../api/queries';
import { EmptyState } from '../feedback/EmptyState';
import { SubmitButton } from '../feedback/SubmitButton';
import { useToast } from '../feedback/ToastProvider';
import {
  describeLearningError,
  useCreateNote,
  useDeleteNote,
  useUpdateNote,
} from './useLearningMutations';

const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

const BODY_MAX_LENGTH = 20000;
const LABEL_MAX_LENGTH = 100;

interface NotesPageProps {
  courseId: string;
}

function NoteCreateForm({
  courseId,
  onDone,
}: {
  courseId: string;
  onDone: () => void;
}): ReactElement {
  const [label, setLabel] = useState('');
  const [body, setBody] = useState('');
  const { showToast } = useToast();
  const createNote = useCreateNote();

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    createNote.mutate(
      { courseId, payload: { label: label || undefined, body } },
      {
        onSuccess: () => {
          setLabel('');
          setBody('');
          onDone();
        },
        onError: (error) => showToast(describeLearningError(error), 'error'),
      },
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="border-border bg-surface mb-4 flex flex-col gap-3 rounded-md border p-4"
    >
      <div className="flex flex-col gap-1">
        <label htmlFor="note-label" className="text-text text-sm font-medium">
          Label (optional)
        </label>
        <input
          id="note-label"
          type="text"
          maxLength={LABEL_MAX_LENGTH}
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          className="border-border bg-surface rounded-sm border px-3 py-2 text-sm"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="note-body" className="text-text text-sm font-medium">
          Note
        </label>
        <textarea
          id="note-body"
          required
          rows={4}
          maxLength={BODY_MAX_LENGTH}
          value={body}
          onChange={(event) => setBody(event.target.value)}
          className="border-border bg-surface rounded-sm border px-3 py-2 text-sm"
        />
      </div>
      <div className="flex gap-2">
        <SubmitButton submitting={createNote.isPending} className={primaryButtonClass}>
          Add note
        </SubmitButton>
        <button type="button" onClick={onDone} className={secondaryButtonClass}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function NoteRow({
  note,
  courseId,
}: {
  note: DispModulesLearningSchemasNoteOut;
  courseId: string;
}): ReactElement {
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState(note.body);
  const { showToast } = useToast();
  const updateNote = useUpdateNote();
  const deleteNote = useDeleteNote();

  function handleSave(event: FormEvent): void {
    event.preventDefault();
    updateNote.mutate(
      { noteId: note.id, courseId, payload: { body } },
      {
        onSuccess: () => setEditing(false),
        onError: (error) => showToast(describeLearningError(error), 'error'),
      },
    );
  }

  return (
    <li className="border-border bg-surface rounded-md border p-3 text-sm">
      {note.label && <p className="text-text-muted mb-1 text-xs font-medium">{note.label}</p>}
      {editing ? (
        <form onSubmit={handleSave} className="flex flex-col gap-2">
          <textarea
            rows={4}
            maxLength={BODY_MAX_LENGTH}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            className="border-border bg-surface rounded-sm border px-3 py-2 text-sm"
          />
          <div className="flex gap-2">
            <button type="submit" disabled={updateNote.isPending} className={secondaryButtonClass}>
              Save
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className={secondaryButtonClass}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <>
          <p className="text-text whitespace-pre-wrap">{note.body}</p>
          <div className="mt-2 flex gap-3">
            <button type="button" onClick={() => setEditing(true)} className="text-accent text-xs">
              Edit
            </button>
            <button
              type="button"
              onClick={() =>
                deleteNote.mutate(
                  { noteId: note.id, courseId },
                  { onError: (error) => showToast(describeLearningError(error), 'error') },
                )
              }
              disabled={deleteNote.isPending}
              className="text-danger text-xs"
            >
              Delete
            </button>
          </div>
        </>
      )}
    </li>
  );
}

/** M20 §23: `/learning/$courseId/notes` — free-form notes anchored (optionally) to a lesson or section. */
export function NotesPage({ courseId }: NotesPageProps): ReactElement {
  const [creating, setCreating] = useState(false);
  const notesQuery = useInfiniteQuery(learningNotesInfiniteQueryOptions(courseId, {}));
  const notes = notesQuery.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <h1>Notes</h1>
        {!creating && (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className={`${primaryButtonClass} inline-flex items-center gap-1.5`}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add note
          </button>
        )}
      </div>

      {creating && <NoteCreateForm courseId={courseId} onDone={() => setCreating(false)} />}

      {notesQuery.isPending && (
        <p aria-busy="true" className="text-text-muted text-sm">
          Loading notes…
        </p>
      )}

      {notesQuery.isSuccess && notes.length === 0 && !creating && (
        <EmptyState icon={NotebookPen} title="No notes yet for this course." />
      )}

      {notes.length > 0 && (
        <ul className="flex flex-col gap-2">
          {notes.map((note) => (
            <NoteRow key={note.id} note={note} courseId={courseId} />
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
    </>
  );
}
