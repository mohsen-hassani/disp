import type { ReactElement } from 'react';
import { useFormContext } from 'react-hook-form';

import type { JsonSchema } from '../types';

interface StringWidgetProps {
  name: string;
  schema: JsonSchema;
  disabled: boolean;
  required: boolean;
  describedBy?: string;
  invalid: boolean;
}

// Appendix B: plain text, or a 4-row textarea once `maxLength` exceeds 200 —
// plus the three recognized `format` values, each mapped to its native
// input type so the browser's own affordances (keyboard, validation UI)
// apply for free.
export function StringWidget({
  name,
  schema,
  disabled,
  required,
  describedBy,
  invalid,
}: StringWidgetProps): ReactElement {
  const { register } = useFormContext();

  if ((schema.maxLength ?? 0) > 200) {
    return (
      <textarea
        id={name}
        rows={4}
        disabled={disabled}
        aria-required={required || undefined}
        aria-describedby={describedBy}
        aria-invalid={invalid || undefined}
        {...register(name)}
      />
    );
  }

  const type =
    schema.format === 'email'
      ? 'email'
      : schema.format === 'uri'
        ? 'url'
        : schema.format === 'date-time'
          ? 'datetime-local'
          : 'text';

  return (
    <input
      id={name}
      type={type}
      disabled={disabled}
      aria-required={required || undefined}
      aria-describedby={describedBy}
      aria-invalid={invalid || undefined}
      {...register(name)}
    />
  );
}
