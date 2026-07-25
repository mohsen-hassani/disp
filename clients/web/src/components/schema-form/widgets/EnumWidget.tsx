import type { ReactElement } from 'react';
import { useFormContext } from 'react-hook-form';

interface EnumWidgetProps {
  name: string;
  options: string[];
  disabled: boolean;
  required: boolean;
  describedBy?: string;
  invalid: boolean;
}

// Appendix B: a select, except a radio group when there are three or fewer
// options — few enough that a single click beats an open-then-choose select.
export function EnumWidget({
  name,
  options,
  disabled,
  required,
  describedBy,
  invalid,
}: EnumWidgetProps): ReactElement {
  const { register } = useFormContext();

  if (options.length <= 3) {
    return (
      <div
        role="radiogroup"
        aria-required={required || undefined}
        aria-describedby={describedBy}
        aria-invalid={invalid || undefined}
        className="flex flex-col gap-1.5"
      >
        {options.map((option) => (
          <label key={option} className="flex items-center gap-2 text-sm">
            <input type="radio" value={option} disabled={disabled} {...register(name)} />
            {option}
          </label>
        ))}
      </div>
    );
  }

  return (
    <select
      id={name}
      disabled={disabled}
      aria-required={required || undefined}
      aria-describedby={describedBy}
      aria-invalid={invalid || undefined}
      {...register(name)}
    >
      <option value="">—</option>
      {options.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
    </select>
  );
}
