import * as Dialog from '@radix-ui/react-dialog';
import { useNavigate } from '@tanstack/react-router';
import { X } from 'lucide-react';
import {
  type ReactElement,
  type ReactNode,
  createContext,
  useContext,
  useId,
  useState,
} from 'react';

import type { ProblemDetail } from '../../api/problem';
import type { ServerFieldError } from '../../lib/mapValidationErrors';
import { useToast } from '../feedback/ToastProvider';
import { NoteEditor } from './NoteEditor';
import { describeNoteError, useCreateNote } from './useNoteMutations';

interface CreateNoteDialogContextValue {
  open: () => void;
}

const CreateNoteDialogContext = createContext<CreateNoteDialogContextValue | null>(null);

/**
 * §16.3: the creation dialog is reachable from the list toolbar, the `n`
 * keyboard shortcut, and (conceptually) the dashboard tile's quick-add —
 * three entry points sharing one dialog instance rather than each mounting
 * its own. Mounted once in `AppShell` so it's available from any screen,
 * matching `n`'s global (not `/notes`-scoped) shortcut table entry.
 */
export function CreateNoteDialogProvider({ children }: { children: ReactNode }): ReactElement {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [serverErrors, setServerErrors] = useState<ServerFieldError[] | undefined>();
  const titleId = useId();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const mutation = useCreateNote();

  return (
    <CreateNoteDialogContext.Provider value={{ open: () => setOpen(true) }}>
      {children}
      <Dialog.Root
        open={open}
        onOpenChange={(next) => {
          if (next) {
            setError(undefined);
            setServerErrors(undefined);
          }
          setOpen(next);
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/40" />
          <Dialog.Content
            aria-labelledby={titleId}
            className="border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4"
          >
            <div className="mb-3 flex items-center justify-between">
              <Dialog.Title id={titleId} className="text-text text-sm font-medium">
                New note
              </Dialog.Title>
              <Dialog.Close
                aria-label="Close"
                className="text-text-muted focus-visible:outline-accent flex h-11 w-11 items-center justify-center rounded-sm focus-visible:outline focus-visible:outline-2"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </Dialog.Close>
            </div>
            <NoteEditor
              mode="create"
              initialBody=""
              submitting={mutation.isPending}
              error={error}
              serverErrors={serverErrors}
              onSubmit={(values) => {
                setError(undefined);
                setServerErrors(undefined);
                mutation.mutate(
                  { title: values.title, body: values.body, pinned: values.pinned },
                  {
                    onSuccess: (note) => {
                      setOpen(false);
                      showToast('Note created.', 'success', {
                        label: 'Open',
                        onClick: () =>
                          void navigate({ to: '/notes/$noteId', params: { noteId: note.id } }),
                      });
                    },
                    onError: (thrown: ProblemDetail) => {
                      if (thrown.status === 422 && thrown.errors) {
                        setServerErrors(thrown.errors);
                      } else {
                        setError(describeNoteError(thrown));
                      }
                    },
                  },
                );
              }}
            />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </CreateNoteDialogContext.Provider>
  );
}

export function useCreateNoteDialog(): CreateNoteDialogContextValue {
  const context = useContext(CreateNoteDialogContext);
  if (!context) {
    throw new Error('useCreateNoteDialog must be used within a CreateNoteDialogProvider');
  }
  return context;
}
