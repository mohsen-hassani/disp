import { zodResolver } from '@hookform/resolvers/zod';
import * as Dialog from '@radix-ui/react-dialog';
import { type ReactElement, useEffect, useId, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import { mapValidationErrors, type ServerFieldError } from '../../lib/mapValidationErrors';
import { SubmitButton } from '../feedback/SubmitButton';

// WEB-SPEC-equivalent bounds, mirrored from `PlantCreate`/`PlantUpdate` (M14 §4).
const NAME_MAX_LENGTH = 120;
const DESCRIPTION_MAX_LENGTH = 2000;
const CARE_NOTES_MAX_LENGTH = 20000;

const plantSchema = z.object({
  name: z
    .string()
    .min(1, 'Name is required')
    .max(NAME_MAX_LENGTH, `Name must be at most ${NAME_MAX_LENGTH} characters.`),
  description: z
    .string()
    .max(
      DESCRIPTION_MAX_LENGTH,
      `Description must be at most ${DESCRIPTION_MAX_LENGTH} characters.`,
    ),
  care_notes: z
    .string()
    .max(CARE_NOTES_MAX_LENGTH, `Care notes must be at most ${CARE_NOTES_MAX_LENGTH} characters.`),
});
type PlantFormValues = z.infer<typeof plantSchema>;
const PLANT_FIELDS = new Set(['name', 'description', 'care_notes']);

export interface PlantEditorSubmitValues {
  name: string;
  description?: string;
  care_notes?: string;
}

interface PlantEditorProps {
  mode: 'create' | 'edit';
  initialName?: string;
  initialDescription?: string;
  initialCareNotes?: string;
  submitting: boolean;
  error?: string;
  /** M14 §6's 422 → field mapping for name/description/care_notes. */
  serverErrors?: ServerFieldError[];
  onSubmit: (values: PlantEditorSubmitValues) => void;
  onCancel: () => void;
}

const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

/**
 * M14 §5: "One `PlantEditor` component with `mode: 'create' | 'edit'`" —
 * both modes share the same field set (unlike `NoteEditor`, whose create
 * and edit modes differ). Care intervals are deliberately not part of this
 * form (M14 §5): they're added on the detail screen once the plant exists.
 */
export function PlantEditor({
  mode,
  initialName,
  initialDescription,
  initialCareNotes,
  submitting,
  error,
  serverErrors,
  onSubmit,
  onCancel,
}: PlantEditorProps): ReactElement {
  const nameId = useId();
  const nameErrorId = useId();
  const descriptionId = useId();
  const descriptionErrorId = useId();
  const careNotesId = useId();
  const careNotesErrorId = useId();
  const [confirmCancelOpen, setConfirmCancelOpen] = useState(false);

  const {
    register,
    handleSubmit,
    setError,
    setFocus,
    formState: { errors, isDirty },
  } = useForm<PlantFormValues>({
    resolver: zodResolver(plantSchema),
    defaultValues: {
      name: initialName ?? '',
      description: initialDescription ?? '',
      care_notes: initialCareNotes ?? '',
    },
  });

  const { fieldErrors: mappedServerErrors, unmapped: unmappedServerErrors } = mapValidationErrors(
    serverErrors ?? [],
    PLANT_FIELDS,
  );

  useEffect(() => {
    for (const { field, message } of mappedServerErrors) {
      setError(field as keyof PlantFormValues, { message });
    }
    if (mappedServerErrors[0]) {
      setFocus(mappedServerErrors[0].field as keyof PlantFormValues);
    }
    // Deliberately keyed on `serverErrors` (and the stable `setError`/`setFocus`) only.
  }, [serverErrors, setError, setFocus]);

  const submit = handleSubmit((values) => {
    onSubmit({
      name: values.name,
      description: values.description || undefined,
      care_notes: values.care_notes || undefined,
    });
  });

  function requestCancel(): void {
    if (isDirty) {
      setConfirmCancelOpen(true);
    } else {
      onCancel();
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor={nameId} className="text-text text-sm font-medium">
            Name *
          </label>
          <input
            id={nameId}
            type="text"
            maxLength={NAME_MAX_LENGTH}
            aria-invalid={errors.name ? true : undefined}
            aria-describedby={errors.name ? nameErrorId : undefined}
            {...register('name')}
          />
          {errors.name && (
            <p id={nameErrorId} role="alert" className="text-danger text-xs">
              {errors.name.message}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor={descriptionId} className="text-text text-sm font-medium">
            Description
          </label>
          <textarea
            id={descriptionId}
            rows={3}
            className="border-border bg-surface min-h-20 rounded-sm border px-3 py-2 text-sm"
            style={{ whiteSpace: 'pre-wrap' }}
            aria-invalid={errors.description ? true : undefined}
            aria-describedby={errors.description ? descriptionErrorId : undefined}
            {...register('description')}
          />
          {errors.description && (
            <p id={descriptionErrorId} role="alert" className="text-danger text-xs">
              {errors.description.message}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor={careNotesId} className="text-text text-sm font-medium">
            Care notes
          </label>
          <textarea
            id={careNotesId}
            rows={6}
            className="border-border bg-surface min-h-32 rounded-sm border px-3 py-2 text-sm"
            style={{ whiteSpace: 'pre-wrap' }}
            aria-invalid={errors.care_notes ? true : undefined}
            aria-describedby={errors.care_notes ? careNotesErrorId : undefined}
            {...register('care_notes')}
          />
          {errors.care_notes && (
            <p id={careNotesErrorId} role="alert" className="text-danger text-xs">
              {errors.care_notes.message}
            </p>
          )}
        </div>

        {(error || unmappedServerErrors.length > 0) && (
          <p role="alert" className="text-danger text-sm">
            {[error, ...unmappedServerErrors.map((e) => e.msg)].filter(Boolean).join(' ')}
          </p>
        )}

        <div className="flex gap-2">
          <SubmitButton submitting={submitting} className={primaryButtonClass}>
            {mode === 'create' ? 'Create plant' : 'Save'}
          </SubmitButton>
          <button type="button" onClick={requestCancel} className={secondaryButtonClass}>
            Cancel
          </button>
        </div>
      </div>

      <Dialog.Root open={confirmCancelOpen} onOpenChange={setConfirmCancelOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/40" />
          <Dialog.Content className="border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4">
            <Dialog.Title className="text-text mb-2 text-sm font-medium">
              Discard changes?
            </Dialog.Title>
            <p className="text-text-muted mb-4 text-sm">You have unsaved changes to this plant.</p>
            <div className="flex justify-end gap-2">
              <Dialog.Close className={secondaryButtonClass}>Keep editing</Dialog.Close>
              <button
                type="button"
                onClick={() => {
                  setConfirmCancelOpen(false);
                  onCancel();
                }}
                className="bg-danger text-accent-text rounded-sm px-3 py-1.5 text-sm font-medium"
              >
                Discard
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </form>
  );
}
