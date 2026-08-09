import { zodResolver } from '@hookform/resolvers/zod';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { type ReactElement, useEffect, useId } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import type { CareIntervalOut } from '../../api/generated';
import type { ProblemDetail } from '../../api/problem';
import { SubmitButton } from '../feedback/SubmitButton';
import { useToast } from '../feedback/ToastProvider';
import { describePlantError, useAddInterval, useUpdateInterval } from './usePlantMutations';

// CareIntervalCreate/Update bounds (src/disp/modules/plants/schemas.py).
const NAME_MAX_LENGTH = 80;
const MIN_INTERVAL_DAYS = 1;
const MAX_INTERVAL_DAYS = 3650;

const intervalSchema = z.object({
  name: z
    .string()
    .min(1, 'Name is required')
    .max(NAME_MAX_LENGTH, `Name must be at most ${NAME_MAX_LENGTH} characters.`),
  // `valueAsNumber` (on the `<input type="number">`'s `register` call below)
  // does the string→number conversion, so this stays a plain `z.number()`
  // — `z.coerce.number()`'s input type is `unknown`, which fights
  // `zodResolver`'s generic inference against `useForm`'s numeric
  // `defaultValues`.
  interval_days: z
    .number({ message: 'Enter a number of days.' })
    .int('Enter a whole number of days.')
    .min(MIN_INTERVAL_DAYS, `Must be at least ${MIN_INTERVAL_DAYS} day.`)
    .max(MAX_INTERVAL_DAYS, `Must be at most ${MAX_INTERVAL_DAYS} days.`),
  last_done_on: z.string(),
  next_due_on: z.string(),
  active: z.boolean(),
});
type IntervalFormValues = z.infer<typeof intervalSchema>;

interface IntervalFormDialogProps {
  plantId: string;
  mode: 'add' | 'edit';
  interval: CareIntervalOut | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const dialogContentClass =
  'border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4';
const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

/**
 * M14 §4: add and edit take different optional fields (`last_done_on` only
 * on add, `next_due_on`/`active` only on edit) — one dialog, gated by
 * `mode`, rather than two near-duplicate forms.
 */
export function IntervalFormDialog({
  plantId,
  mode,
  interval,
  open,
  onOpenChange,
}: IntervalFormDialogProps): ReactElement {
  const titleId = useId();
  const { showToast } = useToast();
  const addMutation = useAddInterval();
  const updateMutation = useUpdateInterval();
  const mutation = mode === 'add' ? addMutation : updateMutation;
  const {
    register,
    handleSubmit,
    reset,
    setError,
    setFocus,
    formState: { errors, isSubmitting },
  } = useForm<IntervalFormValues>({
    resolver: zodResolver(intervalSchema),
    defaultValues: { name: '', interval_days: 7, last_done_on: '', next_due_on: '', active: true },
  });

  useEffect(() => {
    if (!open) {
      return;
    }
    if (mode === 'edit' && interval) {
      reset({
        name: interval.name,
        interval_days: interval.interval_days,
        last_done_on: '',
        next_due_on: '',
        active: interval.active,
      });
    } else {
      reset({ name: '', interval_days: 7, last_done_on: '', next_due_on: '', active: true });
    }
  }, [open, mode, interval, reset]);

  const onSubmit = handleSubmit(async (values) => {
    try {
      if (mode === 'add') {
        await addMutation.mutateAsync({
          plantId,
          payload: {
            name: values.name,
            interval_days: values.interval_days,
            last_done_on: values.last_done_on || undefined,
          },
        });
      } else {
        if (!interval) {
          return;
        }
        await updateMutation.mutateAsync({
          plantId,
          intervalId: interval.id,
          payload: {
            name: values.name,
            interval_days: values.interval_days,
            next_due_on: values.next_due_on || undefined,
            active: values.active,
          },
        });
      }
      onOpenChange(false);
      showToast(mode === 'add' ? 'Care interval added.' : 'Care interval updated.', 'success');
    } catch (thrown) {
      const problem = thrown as ProblemDetail;
      if (problem.code === 'modules.plants.future_date') {
        setError('last_done_on', { message: problem.detail || 'Enter a date in the past.' });
        setFocus('last_done_on');
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
              {mode === 'add' ? 'Add care interval' : `Edit "${interval?.name}"`}
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
              <label htmlFor="interval-name" className="text-text text-sm font-medium">
                Name
              </label>
              <input
                id="interval-name"
                type="text"
                maxLength={NAME_MAX_LENGTH}
                placeholder="Water"
                aria-invalid={errors.name ? true : undefined}
                aria-describedby={errors.name ? 'interval-name-error' : undefined}
                {...register('name')}
              />
              {errors.name && (
                <p id="interval-name-error" role="alert" className="text-danger text-xs">
                  {errors.name.message}
                </p>
              )}
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="interval-days" className="text-text text-sm font-medium">
                Repeat every (days)
              </label>
              <input
                id="interval-days"
                type="number"
                min={MIN_INTERVAL_DAYS}
                max={MAX_INTERVAL_DAYS}
                aria-invalid={errors.interval_days ? true : undefined}
                aria-describedby={errors.interval_days ? 'interval-days-error' : undefined}
                {...register('interval_days', { valueAsNumber: true })}
              />
              {errors.interval_days && (
                <p id="interval-days-error" role="alert" className="text-danger text-xs">
                  {errors.interval_days.message}
                </p>
              )}
            </div>

            {mode === 'add' && (
              <div className="flex flex-col gap-1">
                <label htmlFor="interval-last-done" className="text-text text-sm font-medium">
                  Last done on
                </label>
                <input
                  id="interval-last-done"
                  type="date"
                  aria-invalid={errors.last_done_on ? true : undefined}
                  aria-describedby={errors.last_done_on ? 'interval-last-done-error' : undefined}
                  {...register('last_done_on')}
                />
                <p className="text-text-muted text-xs">
                  Leave blank to schedule the first occurrence from today.
                </p>
                {errors.last_done_on && (
                  <p id="interval-last-done-error" role="alert" className="text-danger text-xs">
                    {errors.last_done_on.message}
                  </p>
                )}
              </div>
            )}

            {mode === 'edit' && (
              <>
                <div className="flex flex-col gap-1">
                  <label htmlFor="interval-next-due" className="text-text text-sm font-medium">
                    Next due on
                  </label>
                  <input id="interval-next-due" type="date" {...register('next_due_on')} />
                  <p className="text-text-muted text-xs">Leave blank to keep the current date.</p>
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" {...register('active')} />
                  Active
                </label>
              </>
            )}

            <SubmitButton
              submitting={isSubmitting || mutation.isPending}
              className={`self-start ${primaryButtonClass}`}
            >
              {mode === 'add' ? 'Add interval' : 'Save'}
            </SubmitButton>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
