import type { ReactElement } from 'react';
import { Controller, useFormContext } from 'react-hook-form';

interface SecretWidgetProps {
  name: string;
  disabled: boolean;
  describedBy?: string;
  invalid: boolean;
}

const MASKED = '***';

// §14.4: a masked value renders *empty* (the literal "***" must never
// appear as visible input text) while the underlying form value stays
// "***" until the user actually types — that's what lets the Set/Clear
// affordances and the submit-time omission (SchemaForm's job, via
// `formState.dirtyFields`) key off the real value rather than a separate
// touched flag. `register()`'s uncontrolled binding can't express "DOM
// value differs from form value," so this needs `Controller`.
export function SecretWidget({
  name,
  disabled,
  describedBy,
  invalid,
}: SecretWidgetProps): ReactElement {
  const { control, setValue } = useFormContext();

  return (
    <Controller
      name={name}
      control={control}
      render={({ field }) => {
        const isMasked = field.value === MASKED;
        const isUnset = field.value === null || field.value === undefined;
        return (
          <div className="flex items-center gap-2">
            <input
              id={name}
              type="password"
              autoComplete="off"
              disabled={disabled}
              placeholder={isMasked ? 'Saved — leave blank to keep' : undefined}
              aria-describedby={describedBy}
              aria-invalid={invalid || undefined}
              value={isMasked ? '' : (field.value ?? '')}
              onChange={field.onChange}
              onBlur={field.onBlur}
              name={field.name}
              ref={field.ref}
            />
            {isMasked && (
              <>
                <span className="bg-surface-sunken text-text-muted rounded-sm px-1.5 py-0.5 text-xs">
                  Set
                </span>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => setValue(name, null, { shouldDirty: true })}
                  className="text-text-muted text-xs underline"
                >
                  Clear
                </button>
              </>
            )}
            {isUnset && (
              <span className="bg-surface-sunken text-text-muted rounded-sm px-1.5 py-0.5 text-xs">
                Not set
              </span>
            )}
          </div>
        );
      }}
    />
  );
}
