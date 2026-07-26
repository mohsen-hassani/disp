import { zodResolver } from '@hookform/resolvers/zod';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { type ReactElement, useEffect, useId } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import type { ProblemDetail } from '../../api/problem';
import { useToast } from '../feedback/ToastProvider';
import { describeNoteError, useShareNote } from './useNoteMutations';

interface ShareDialogProps {
  noteId: string | null;
  noteHeading: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const shareSchema = z.object({
  email: z.string().min(1, 'Email is required').email('Enter a valid email address.'),
  permission: z.enum(['read', 'write']),
});
type ShareFormValues = z.infer<typeof shareSchema>;

const dialogContentClass =
  'border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4';
const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

/** §16.4: no endpoint lists existing shares — the dialog states sharing is additive and nothing more. */
export function ShareDialog({
  noteId,
  noteHeading,
  open,
  onOpenChange,
}: ShareDialogProps): ReactElement {
  const titleId = useId();
  const { showToast } = useToast();
  const mutation = useShareNote(noteId ?? '');
  const {
    register,
    handleSubmit,
    reset,
    setError,
    setFocus,
    formState: { errors, isSubmitting },
  } = useForm<ShareFormValues>({
    resolver: zodResolver(shareSchema),
    defaultValues: { email: '', permission: 'read' },
  });

  useEffect(() => {
    if (open) {
      reset({ email: '', permission: 'read' });
    }
  }, [open, reset]);

  const onSubmit = handleSubmit(async (values) => {
    if (!noteId) {
      return;
    }
    try {
      await mutation.mutateAsync({ email: values.email, permission: values.permission });
      onOpenChange(false);
      showToast(`Shared with ${values.email}.`);
    } catch (thrown) {
      const problem = thrown as ProblemDetail;
      if (problem.code === 'notes.user_not_found') {
        setError('email', {
          message: 'No user with that email. They need an account first.',
        });
        setFocus('email');
        return;
      }
      if (problem.code === 'notes.cannot_share_with_self') {
        setError('email', { message: problem.detail || 'You cannot share a note with yourself.' });
        setFocus('email');
        return;
      }
      if (problem.status === 403) {
        onOpenChange(false);
        showToast('Only the owner can share this note.', 'danger');
        return;
      }
      showToast(describeNoteError(problem), 'danger');
    }
  });

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content aria-labelledby={titleId} className={dialogContentClass}>
          <div className="mb-3 flex items-center justify-between">
            <Dialog.Title id={titleId} className="text-text text-sm font-medium">
              Share &quot;{noteHeading}&quot;
            </Dialog.Title>
            <Dialog.Close
              aria-label="Close"
              className="text-text-muted focus-visible:outline-accent rounded-sm p-1 focus-visible:outline focus-visible:outline-2"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </Dialog.Close>
          </div>
          <p className="text-text-muted mb-4 text-sm">
            Sharing is additive — this only grants access, it doesn&apos;t show who already has it.
            Removing access requires the API.
          </p>
          <form
            onSubmit={(event) => void onSubmit(event)}
            noValidate
            className="flex flex-col gap-4"
          >
            <div className="flex flex-col gap-1">
              <label htmlFor="share-email" className="text-text text-sm font-medium">
                Email
              </label>
              <input
                id="share-email"
                type="email"
                aria-invalid={errors.email ? true : undefined}
                aria-describedby={errors.email ? 'share-email-error' : undefined}
                {...register('email')}
              />
              {errors.email && (
                <p id="share-email-error" role="alert" className="text-danger text-xs">
                  {errors.email.message}
                </p>
              )}
            </div>
            <fieldset className="flex flex-col gap-2">
              <legend className="text-text text-sm font-medium">Permission</legend>
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" value="read" {...register('permission')} />
                Read — can view only
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" value="write" {...register('permission')} />
                Write — can view and edit
              </label>
            </fieldset>
            <button
              type="submit"
              disabled={isSubmitting || !noteId}
              className={`self-start ${primaryButtonClass}`}
            >
              {isSubmitting ? 'Sharing…' : 'Share'}
            </button>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
