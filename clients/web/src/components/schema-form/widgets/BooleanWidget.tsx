import * as Switch from '@radix-ui/react-switch';
import type { ReactElement } from 'react';
import { Controller, useFormContext } from 'react-hook-form';

interface BooleanWidgetProps {
  name: string;
  disabled: boolean;
  describedBy?: string;
}

export function BooleanWidget({ name, disabled, describedBy }: BooleanWidgetProps): ReactElement {
  const { control } = useFormContext();
  return (
    <Controller
      name={name}
      control={control}
      render={({ field }) => (
        <Switch.Root
          id={name}
          checked={Boolean(field.value)}
          onCheckedChange={field.onChange}
          disabled={disabled}
          aria-describedby={describedBy}
          className="bg-surface-sunken data-[state=checked]:bg-accent focus-visible:outline-accent relative h-6 w-10 rounded-full transition-colors duration-fast focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 motion-reduce:transition-none"
        >
          <Switch.Thumb className="bg-surface block h-5 w-5 translate-x-0.5 rounded-full transition-transform duration-fast data-[state=checked]:translate-x-[18px] motion-reduce:transition-none" />
        </Switch.Root>
      )}
    />
  );
}
