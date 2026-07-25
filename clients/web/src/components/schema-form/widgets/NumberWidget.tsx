import type { ReactElement } from 'react';
import { useFormContext } from 'react-hook-form';

interface NumberWidgetProps {
  name: string;
  integer: boolean;
  disabled: boolean;
  required: boolean;
  describedBy?: string;
  invalid: boolean;
}

export function NumberWidget({
  name,
  integer,
  disabled,
  required,
  describedBy,
  invalid,
}: NumberWidgetProps): ReactElement {
  const { register } = useFormContext();
  return (
    <input
      id={name}
      type="number"
      step={integer ? 1 : 'any'}
      disabled={disabled}
      aria-required={required || undefined}
      aria-describedby={describedBy}
      aria-invalid={invalid || undefined}
      {...register(name, { valueAsNumber: true })}
    />
  );
}
