import { zodResolver } from '@hookform/resolvers/zod';
import * as Dialog from '@radix-ui/react-dialog';
import { useBlocker } from '@tanstack/react-router';
import { type ReactElement, useEffect, useId, useRef } from 'react';
import { FormProvider, useForm } from 'react-hook-form';
import type { z } from 'zod';

import { FieldFor } from './fieldFor';
import { schemaToZod } from './schemaToZod';
import type { JsonSchema, JsonSchemaDoc } from './types';

export interface ServerFieldError {
  loc: Array<string | number>;
  msg: string;
}

export interface SchemaFormProps {
  schema: JsonSchemaDoc;
  initialValue: Record<string, unknown>;
  /**
   * `dirtyFields` lets the caller send only changed keys where that
   * matters (§14.1's settings `PUT`, rule 6) — a tile action (§13.6) just
   * uses the full `values` object instead. SchemaForm doesn't decide which;
   * it hands both to whichever screen owns that call.
   */
  onSubmit: (
    values: Record<string, unknown>,
    dirtyFields: Record<string, unknown>,
  ) => Promise<void> | void;
  submitLabel?: string;
  /** Form-level error rendered inline (§13.6: a failed action keeps the dialog open with the error inline). */
  error?: string;
  /** §19.3's 422 → field mapping. Re-applied whenever this array's identity changes. */
  serverErrors?: ServerFieldError[];
  disabled?: boolean;
}

function buildDefaultValues(
  schema: JsonSchemaDoc,
  initialValue: Record<string, unknown>,
): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const [key, propSchema] of Object.entries(schema.properties ?? {})) {
    if (key in initialValue) {
      values[key] = initialValue[key];
    } else if ('default' in propSchema) {
      values[key] = propSchema.default;
    }
  }
  return values;
}

function isSecret(schema: JsonSchema): boolean {
  return schema['x-secret'] === true;
}

// WEB-SPEC §19.3: drop a leading body/query/path segment, join the rest
// with '.' to get the react-hook-form field name. A name that isn't one of
// this form's own top-level properties is reported back as unmapped so the
// caller can fall back to a form-level message instead of silently
// discarding it.
const LOC_PREFIXES = new Set(['body', 'query', 'path']);

function trimLocPrefix(loc: Array<string | number>): Array<string | number> {
  return loc.length > 0 && typeof loc[0] === 'string' && LOC_PREFIXES.has(loc[0])
    ? loc.slice(1)
    : loc;
}

// §14.2/§14.3: the generic settings-panel-and-tile-action-body renderer —
// no `@rjsf/core`, no per-schema-shape special casing. Reused by both
// TileActionDialog (M05) and the settings screens (M06).
export function SchemaForm(props: SchemaFormProps): ReactElement {
  const {
    schema,
    initialValue,
    onSubmit,
    submitLabel = 'Save',
    error,
    serverErrors,
    disabled = false,
  } = props;
  const defs = schema.$defs ?? {};
  // The schema (and therefore its shape) is only known at runtime — cast
  // through `unknown` rather than fight Zod/RHF's generic inference for a
  // form whose field set is inherently dynamic.
  const zodSchema = schemaToZod(schema, defs) as unknown as z.ZodType<
    Record<string, unknown>,
    Record<string, unknown>
  >;
  const methods = useForm<Record<string, unknown>>({
    resolver: zodResolver(zodSchema),
    defaultValues: buildDefaultValues(schema, initialValue),
    // §19.4: validate on blur and on submit; only re-validate on change
    // after a field has already failed once.
    mode: 'onBlur',
    reValidateMode: 'onChange',
  });
  const {
    handleSubmit,
    setError,
    setFocus,
    reset,
    formState: { isSubmitting, isDirty, dirtyFields },
  } = methods;
  const requiredKeys = new Set(schema.required ?? []);
  const propertyKeys = new Set(Object.keys(schema.properties ?? {}));

  // §14.5: "success → ... dirty-state reset to the server's response."
  // `defaultValues` is only read once at mount by react-hook-form itself —
  // this is what makes a *later* `initialValue` change (the settings
  // screen writing the PUT response into the query cache it reads
  // `initialValue` from) actually take effect. Keyed on reference equality
  // deliberately: typing doesn't change the caller's `initialValue` prop,
  // only the caller re-rendering with fresh server data does.
  const previousInitialValueRef = useRef(initialValue);
  useEffect(() => {
    if (previousInitialValueRef.current !== initialValue) {
      previousInitialValueRef.current = initialValue;
      reset(buildDefaultValues(schema, initialValue));
    }
  }, [initialValue, schema, reset]);

  const unmappedServerErrors = (serverErrors ?? []).filter(
    ({ loc }) => !propertyKeys.has(String(trimLocPrefix(loc)[0])),
  );

  useEffect(() => {
    for (const { loc, msg } of serverErrors ?? []) {
      const trimmed = trimLocPrefix(loc);
      if (propertyKeys.has(String(trimmed[0]))) {
        setError(trimmed.join('.'), { message: msg });
      }
    }
    // Deliberately keyed on `serverErrors` (and the stable `setError`) only
    // — `propertyKeys`/`schema` don't change within one form's lifetime.
  }, [serverErrors, setError]);

  // §14.3 rule 7: warn on navigating away with unsaved changes. Applies
  // equally whether SchemaForm renders directly in a route (M06's settings
  // screens) or inside a dialog (M05's TileActionDialog) — a modal losing
  // typed input to an accidental back-navigation is the same problem.
  const blocker = useBlocker({
    shouldBlockFn: () => isDirty && !isSubmitting,
    enableBeforeUnload: () => isDirty && !isSubmitting,
    withResolver: true,
  });
  const blockerTitleId = useId();

  const submit = handleSubmit(
    async (values) => {
      // §14.4 rule 3: an untouched secret is omitted entirely — never sent
      // back as the literal "***", even though the server tolerates it.
      const payload = { ...values };
      for (const [key, propSchema] of Object.entries(schema.properties ?? {})) {
        if (isSecret(propSchema) && !dirtyFields[key]) {
          delete payload[key];
        }
      }
      await onSubmit(payload, dirtyFields);
    },
    (formErrors) => {
      // §19.4: the first invalid field receives focus on a failed submit.
      const [firstField] = Object.keys(formErrors);
      if (firstField) {
        setFocus(firstField);
      }
    },
  );

  return (
    <FormProvider {...methods}>
      <form onSubmit={(event) => void submit(event)} noValidate className="flex flex-col gap-4">
        {Object.entries(schema.properties ?? {}).map(([key, propSchema]) => (
          <FieldFor
            key={key}
            name={key}
            schema={propSchema}
            defs={defs}
            depth={1}
            required={requiredKeys.has(key)}
            disabled={disabled || isSubmitting}
          />
        ))}
        {(error || unmappedServerErrors.length > 0) && (
          <p role="alert" className="text-danger text-sm">
            {[error, ...unmappedServerErrors.map((e) => e.msg)].filter(Boolean).join(' ')}
          </p>
        )}
        <button
          type="submit"
          disabled={disabled || isSubmitting}
          className="bg-accent text-accent-text focus-visible:outline-accent self-start rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60"
        >
          {isSubmitting ? 'Saving…' : submitLabel}
        </button>
      </form>

      <Dialog.Root
        open={blocker.status === 'blocked'}
        onOpenChange={(open) => !open && blocker.reset?.()}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/40" />
          <Dialog.Content
            aria-labelledby={blockerTitleId}
            className="border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4"
          >
            <Dialog.Title id={blockerTitleId} className="text-text mb-2 text-sm font-medium">
              Leave without saving?
            </Dialog.Title>
            <p className="text-text-muted mb-4 text-sm">Your changes haven&apos;t been saved.</p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => blocker.reset?.()}
                className="border-border text-text rounded-sm border px-3 py-1.5 text-sm"
              >
                Stay
              </button>
              <button
                type="button"
                onClick={() => blocker.proceed?.()}
                className="bg-danger text-accent-text rounded-sm px-3 py-1.5 text-sm font-medium"
              >
                Leave
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </FormProvider>
  );
}
