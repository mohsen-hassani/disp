import type { ReactElement } from 'react';

import { FieldFor } from '../fieldFor';
import type { JsonSchema } from '../types';

interface ObjectWidgetProps {
  name: string;
  schema: JsonSchema;
  defs: Record<string, JsonSchema>;
  depth: number;
  disabled: boolean;
}

// Appendix B: a nested fieldset with a legend, recursing back through
// `FieldFor` for each property — `depth` is already incremented by the
// caller (`fieldFor.tsx`'s dispatch), which is also what enforces the
// three-level nesting cap.
export function ObjectWidget({
  name,
  schema,
  defs,
  depth,
  disabled,
}: ObjectWidgetProps): ReactElement {
  const required = new Set(schema.required ?? []);
  return (
    <fieldset className="border-border flex flex-col gap-3 rounded-sm border p-3">
      <legend className="text-text px-1 text-sm font-medium">{schema.title ?? 'Details'}</legend>
      {Object.entries(schema.properties ?? {}).map(([key, propSchema]) => (
        <FieldFor
          key={key}
          name={`${name}.${key}`}
          schema={propSchema}
          defs={defs}
          depth={depth}
          required={required.has(key)}
          disabled={disabled}
        />
      ))}
    </fieldset>
  );
}
