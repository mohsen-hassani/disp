import { zodResolver } from '@hookform/resolvers/zod';
import * as Dialog from '@radix-ui/react-dialog';
import * as Switch from '@radix-ui/react-switch';
import { type KeyboardEvent, type ReactElement, useEffect, useId, useRef, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { z } from 'zod';

const BODY_MAX_LENGTH = 20000;
const COUNTER_THRESHOLD = 19000;

const noteSchema = z.object({
  title: z.string().optional(),
  body: z
    .string()
    .min(1, 'Body is required')
    .max(BODY_MAX_LENGTH, `Body must be at most ${BODY_MAX_LENGTH} characters.`),
  pinned: z.boolean(),
});
type NoteFormValues = z.infer<typeof noteSchema>;

export interface NoteEditorSubmitValues {
  title?: string;
  body: string;
  pinned?: boolean;
}

interface NoteEditorProps {
  mode: 'create' | 'edit';
  initialTitle?: string;
  initialBody: string;
  initialPinned?: boolean;
  submitting: boolean;
  error?: string;
  onSubmit: (values: NoteEditorSubmitValues) => void;
  onCancel?: () => void;
}

const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

/**
 * §16.3's creation form (title/body/pin) and §16.2's inline body-only edit
 * share this one component (`mode` picks the field set) — both need the
 * same body textarea, char counter, and `Cmd/Ctrl+Enter`-submits behavior;
 * only edit mode additionally supports `Escape`-cancels-with-confirmation,
 * since create mode already runs inside a `Dialog` whose own Escape
 * handling closes it (§16.3 states no unsaved-changes guard there).
 */
export function NoteEditor({
  mode,
  initialTitle,
  initialBody,
  initialPinned,
  submitting,
  error,
  onSubmit,
  onCancel,
}: NoteEditorProps): ReactElement {
  const titleId = useId();
  const bodyId = useId();
  const bodyErrorId = useId();
  const pinnedId = useId();
  const [confirmCancelOpen, setConfirmCancelOpen] = useState(false);
  const bodyRef = useRef<HTMLTextAreaElement | null>(null);

  const {
    register,
    handleSubmit,
    control,
    watch,
    formState: { errors, isDirty },
  } = useForm<NoteFormValues>({
    resolver: zodResolver(noteSchema),
    defaultValues: {
      title: initialTitle ?? '',
      body: initialBody,
      pinned: initialPinned ?? false,
    },
  });
  const { ref: registerBodyRef, ...bodyField } = register('body');

  const bodyLength = watch('body')?.length ?? 0;

  useEffect(() => {
    // Only on mount — `mode` never changes for a given instance (a create
    // dialog remounts fresh each time it opens, per `CreateNoteDialogProvider`).
    if (mode === 'create') {
      bodyRef.current?.focus();
    }
  }, []);

  const submit = handleSubmit((values) => {
    onSubmit({
      title: mode === 'create' ? values.title || undefined : undefined,
      body: values.body,
      pinned: mode === 'create' ? values.pinned : undefined,
    });
  });

  function requestCancel(): void {
    if (isDirty) {
      setConfirmCancelOpen(true);
    } else {
      onCancel?.();
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement | HTMLInputElement>): void {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault();
      void submit();
      return;
    }
    if (mode === 'edit' && event.key === 'Escape') {
      event.preventDefault();
      requestCancel();
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate>
      <div className="flex flex-col gap-4">
        {mode === 'create' && (
          <div className="flex flex-col gap-1">
            <label htmlFor={titleId} className="text-text text-sm font-medium">
              Title (optional)
            </label>
            <input id={titleId} type="text" onKeyDown={handleKeyDown} {...register('title')} />
          </div>
        )}

        <div className="flex flex-col gap-1">
          <label htmlFor={bodyId} className="text-text text-sm font-medium">
            Body{mode === 'create' ? ' *' : ''}
          </label>
          <textarea
            id={bodyId}
            rows={mode === 'create' ? 6 : 12}
            className="border-border bg-surface min-h-32 rounded-sm border px-3 py-2 text-sm"
            style={{ whiteSpace: 'pre-wrap' }}
            aria-invalid={errors.body ? true : undefined}
            aria-describedby={errors.body ? bodyErrorId : undefined}
            onKeyDown={handleKeyDown}
            ref={(element) => {
              registerBodyRef(element);
              bodyRef.current = element;
            }}
            {...bodyField}
          />
          {errors.body && (
            <p id={bodyErrorId} role="alert" className="text-danger text-xs">
              {errors.body.message}
            </p>
          )}
          {bodyLength > COUNTER_THRESHOLD && (
            <p aria-live="polite" className="text-text-muted text-xs">
              {bodyLength} / {BODY_MAX_LENGTH}
            </p>
          )}
        </div>

        {mode === 'create' && (
          <div className="flex items-center gap-2 text-sm">
            <Controller
              name="pinned"
              control={control}
              render={({ field }) => (
                <Switch.Root
                  id={pinnedId}
                  checked={field.value}
                  onCheckedChange={field.onChange}
                  className="bg-surface-sunken data-[state=checked]:bg-accent focus-visible:outline-accent relative h-6 w-10 rounded-full transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                >
                  <Switch.Thumb className="bg-surface block h-5 w-5 translate-x-0.5 rounded-full transition-transform data-[state=checked]:translate-x-[18px]" />
                </Switch.Root>
              )}
            />
            <label htmlFor={pinnedId} className="text-text text-sm font-medium">
              Pin this note
            </label>
          </div>
        )}

        {error && (
          <p role="alert" className="text-danger text-sm">
            {error}
          </p>
        )}

        <div className="flex gap-2">
          <button type="submit" disabled={submitting} className={primaryButtonClass}>
            {mode === 'create'
              ? submitting
                ? 'Creating…'
                : 'Create note'
              : submitting
                ? 'Saving…'
                : 'Save'}
          </button>
          {mode === 'edit' && (
            <button type="button" onClick={requestCancel} className={secondaryButtonClass}>
              Cancel
            </button>
          )}
        </div>
      </div>

      <Dialog.Root open={confirmCancelOpen} onOpenChange={setConfirmCancelOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/40" />
          <Dialog.Content className="border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4">
            <Dialog.Title className="text-text mb-2 text-sm font-medium">
              Discard changes?
            </Dialog.Title>
            <p className="text-text-muted mb-4 text-sm">You have unsaved changes to this note.</p>
            <div className="flex justify-end gap-2">
              <Dialog.Close className={secondaryButtonClass}>Keep editing</Dialog.Close>
              <button
                type="button"
                onClick={() => {
                  setConfirmCancelOpen(false);
                  onCancel?.();
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
