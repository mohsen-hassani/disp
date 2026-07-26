import { Plus, Trash2 } from 'lucide-react';
import type { ReactElement } from 'react';
import { useFieldArray, useFormContext } from 'react-hook-form';

import { FieldFor } from '../fieldFor';
import { type JsonSchema, resolveSchema } from '../types';

interface ArrayWidgetProps {
  name: string;
  itemSchema: JsonSchema;
  defs: Record<string, JsonSchema>;
  depth: number;
  disabled: boolean;
}

// Appendix B's two array rows — string items and object items — share one
// component: repeatable rows with Add/Remove, differing only in whether a
// row is a single text input or a nested set of fields.
export function ArrayWidget({
  name,
  itemSchema,
  defs,
  depth,
  disabled,
}: ArrayWidgetProps): ReactElement {
  const { control, register } = useFormContext();
  const { fields, append, remove } = useFieldArray({ control, name });
  const { schema: resolvedItemSchema } = resolveSchema(itemSchema, defs);
  const isObjectItems =
    resolvedItemSchema.type === 'object' && Boolean(resolvedItemSchema.properties);
  const requiredKeys = new Set(resolvedItemSchema.required ?? []);

  return (
    <div className="flex flex-col gap-2">
      {fields.map((field, index) => (
        <div key={field.id} className="border-border flex items-start gap-2 rounded-sm border p-2">
          <div className="flex flex-1 flex-col gap-2">
            {isObjectItems ? (
              Object.entries(resolvedItemSchema.properties ?? {}).map(([key, propSchema]) => (
                <FieldFor
                  key={key}
                  name={`${name}.${index}.${key}`}
                  schema={propSchema}
                  defs={defs}
                  depth={depth + 1}
                  required={requiredKeys.has(key)}
                  disabled={disabled}
                />
              ))
            ) : (
              <input
                aria-label={`Item ${index + 1}`}
                disabled={disabled}
                {...register(`${name}.${index}` as const)}
              />
            )}
          </div>
          <button
            type="button"
            onClick={() => remove(index)}
            disabled={disabled}
            aria-label={`Remove item ${index + 1}`}
            className="text-text-muted focus-visible:outline-accent flex h-11 w-11 items-center justify-center rounded-sm focus-visible:outline focus-visible:outline-2"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => append(isObjectItems ? {} : '')}
        disabled={disabled}
        className="border-border text-text-muted flex items-center gap-1.5 self-start rounded-sm border border-dashed px-2 py-1 text-sm"
      >
        <Plus className="h-4 w-4" aria-hidden="true" />
        Add
      </button>
    </div>
  );
}
