import { zodResolver } from '@hookform/resolvers/zod';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { type ReactElement, useEffect, useId } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import type { CareIntervalOut } from '../../api/generated';
import type { ProblemDetail } from '../../api/problem';
import { dateOnly } from '../../lib/format';
import { SubmitButton } from '../feedback/SubmitButton';
import { useToast } from '../feedback/ToastProvider';
import { describePlantError, useCompleteInterval } from './usePlantMutations';

// CompleteRequest.note ≤2000 (src/disp/modules/plants/schemas.py).
const NOTE_MAX_LENGTH = 2000;

const completeSchema = z.object({
  completed_on: z.string(),
  note: z.string().max(NOTE_MAX_LENGTH, `Note must be at most ${NOTE_MAX_LENGTH} characters.`),
});
type CompleteFormValues = z.infer<typeof completeSchema>;

interface CompleteDialogProps {
  plantId: string;
  interval: CareIntervalOut | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const dialogContentClass =
  'border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4';
const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

/**
 * M14 §1/§5: "Mark done" never predicts the next due date — an empty
 * `completed_on` lets the server default to today, and `dateOnly` on the
 * returned `interval.next_due_on` is what actually gets shown, not
 * anything computed here. Back-dating up to a year is the point of the
 * field (§1); future dates are rejected by the server (§5's `plants.
 * future_date`/`plants.date_too_old`) and surfaced inline rather than
 * pre-validated client-side, since a client-side rule could drift from the
 * server's.
 */
export function CompleteDialog({
  plantId,
  interval,
  open,
  onOpenChange,
}: CompleteDialogProps): ReactElement {
  const titleId = useId();
  const { showToast } = useToast();
  const mutation = useCompleteInterval();
  const {
    register,
    handleSubmit,
    reset,
    setError,
    setFocus,
    formState: { errors, isSubmitting },
  } = useForm<CompleteFormValues>({
    resolver: zodResolver(completeSchema),
    defaultValues: { completed_on: '', note: '' },
  });

  useEffect(() => {
    if (open) {
      reset({ completed_on: '', note: '' });
    }
  }, [open, reset]);

  const onSubmit = handleSubmit(async (values) => {
    if (!interval) {
      return;
    }
    try {
      const result = await mutation.mutateAsync({
        plantId,
        intervalId: interval.id,
        payload: {
          completed_on: values.completed_on || undefined,
          note: values.note || undefined,
        },
      });
      onOpenChange(false);
      showToast(
        `Marked "${interval.name}" done. Next due ${dateOnly(result.interval.next_due_on)}.`,
        'success',
      );
    } catch (thrown) {
      const problem = thrown as ProblemDetail;
      if (problem.code === 'plants.future_date' || problem.code === 'plants.date_too_old') {
        setError('completed_on', { message: problem.detail || 'Enter a valid completion date.' });
        setFocus('completed_on');
        return;
      }
      showToast(describePlantError(problem), 'error');
    }
  });

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content aria-labelledby={titleId} className={dialogContentClass}>
          <div className="mb-3 flex items-center justify-between">
            <Dialog.Title id={titleId} className="text-text text-sm font-medium">
              Mark &quot;{interval?.name}&quot; done
            </Dialog.Title>
            <Dialog.Close
              aria-label="Close"
              className="text-text-muted focus-visible:outline-accent flex h-11 w-11 items-center justify-center rounded-sm focus-visible:outline focus-visible:outline-2"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </Dialog.Close>
          </div>
          <form
            onSubmit={(event) => void onSubmit(event)}
            noValidate
            className="flex flex-col gap-4"
          >
            <div className="flex flex-col gap-1">
              <label htmlFor="complete-on" className="text-text text-sm font-medium">
                Completed on
              </label>
              <input
                id="complete-on"
                type="date"
                aria-invalid={errors.completed_on ? true : undefined}
                aria-describedby={errors.completed_on ? 'complete-on-error' : undefined}
                {...register('completed_on')}
              />
              <p className="text-text-muted text-xs">Leave blank to use today.</p>
              {errors.completed_on && (
                <p id="complete-on-error" role="alert" className="text-danger text-xs">
                  {errors.completed_on.message}
                </p>
              )}
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="complete-note" className="text-text text-sm font-medium">
                Note
              </label>
              <textarea
                id="complete-note"
                rows={3}
                maxLength={NOTE_MAX_LENGTH}
                aria-invalid={errors.note ? true : undefined}
                aria-describedby={errors.note ? 'complete-note-error' : undefined}
                {...register('note')}
              />
              {errors.note && (
                <p id="complete-note-error" role="alert" className="text-danger text-xs">
                  {errors.note.message}
                </p>
              )}
            </div>
            <SubmitButton
              submitting={isSubmitting || mutation.isPending}
              disabled={!interval}
              className={`self-start ${primaryButtonClass}`}
            >
              Mark done
            </SubmitButton>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
