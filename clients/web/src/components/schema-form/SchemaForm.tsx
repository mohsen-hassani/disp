import { zodResolver } from '@hookform/resolvers/zod';
import type { ReactElement } from 'react';
import { FormProvider, useForm } from 'react-hook-form';
import type { z } from 'zod';

import { FieldFor } from './fieldFor';
import { schemaToZod } from './schemaToZod';
import type { JsonSchema, JsonSchemaDoc } from './types';

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

// §14.2/§14.3: the generic settings-panel-and-tile-action-body renderer —
// no `@rjsf/core`, no per-schema-shape special casing. Reused by both
// TileActionDialog (M05) and the settings screens (M06, not yet built);
// §14.3 rule 7 (warn on navigate-away via the router's `blocker`) is left
// to M06, since it needs the `/settings/:domain` route this milestone
// doesn't render into.
export function SchemaForm(props: SchemaFormProps): ReactElement {
  const { schema, initialValue, onSubmit, submitLabel = 'Save', error, disabled = false } = props;
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
  });
  const {
    handleSubmit,
    formState: { isSubmitting, dirtyFields },
  } = methods;
  const requiredKeys = new Set(schema.required ?? []);

  const submit = handleSubmit(async (values) => {
    // §14.4 rule 3: an untouched secret is omitted entirely — never sent
    // back as the literal "***", even though the server tolerates it.
    const payload = { ...values };
    for (const [key, propSchema] of Object.entries(schema.properties ?? {})) {
      if (isSecret(propSchema) && !dirtyFields[key]) {
        delete payload[key];
      }
    }
    await onSubmit(payload, dirtyFields);
  });

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
        {error && (
          <p role="alert" className="text-danger text-sm">
            {error}
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
    </FormProvider>
  );
}
