import type { ReactElement, ReactNode } from 'react';
import { useFormContext } from 'react-hook-form';

import { BooleanWidget } from './widgets/BooleanWidget';
import { EnumWidget } from './widgets/EnumWidget';
import { FallbackWidget } from './widgets/FallbackWidget';
import { NumberWidget } from './widgets/NumberWidget';
import { ObjectWidget } from './widgets/ObjectWidget';
import { SecretWidget } from './widgets/SecretWidget';
import { StringWidget } from './widgets/StringWidget';
import { ArrayWidget } from './widgets/ArrayWidget';
import { type JsonSchema, resolveSchema } from './types';

const MAX_NESTING_DEPTH = 3;

export interface FieldForProps {
  name: string;
  schema: JsonSchema;
  defs: Record<string, JsonSchema>;
  /** 1 at the form's own top level; each nested object/array-of-object adds one. */
  depth: number;
  required: boolean;
  disabled: boolean;
}

function humanize(name: string): string {
  const last = name.split('.').at(-1) ?? name;
  return last.charAt(0).toUpperCase() + last.slice(1).replace(/([A-Z])/g, ' $1');
}

function errorAt(errors: Record<string, unknown>, path: string): string | undefined {
  const message = path.split('.').reduce<unknown>((node, key) => {
    if (node && typeof node === 'object' && key in node) {
      return (node as Record<string, unknown>)[key];
    }
    return undefined;
  }, errors);
  if (message && typeof message === 'object' && 'message' in message) {
    const value = (message as { message?: unknown }).message;
    return typeof value === 'string' ? value : undefined;
  }
  return undefined;
}

// Appendix B's dispatch table, in one place — every widget file above
// renders exactly one row of that table. Field chrome (label/description/
// error) lives here rather than per-widget, so a widget only ever renders
// its own control.
export function FieldFor(props: FieldForProps): ReactElement {
  const { name, schema: rawSchema, defs, depth, required, disabled } = props;
  const {
    formState: { errors },
  } = useFormContext();
  const { schema, nullable } = resolveSchema(rawSchema, defs);
  const label = schema.title ?? humanize(name);
  const errorMessage = errorAt(errors, name);
  const isRequired = required && !nullable;

  const descriptionId = schema.description ? `${name}-description` : undefined;
  const errorId = errorMessage ? `${name}-error` : undefined;
  const describedBy = [descriptionId, errorId].filter(Boolean).join(' ') || undefined;

  return (
    <FieldShell
      name={name}
      label={label}
      description={schema.description}
      error={errorMessage}
      required={isRequired}
    >
      {renderControl({
        name,
        schema,
        defs,
        depth,
        required: isRequired,
        disabled,
        describedBy,
        invalid: Boolean(errorMessage),
      })}
    </FieldShell>
  );
}

// Appendix B's array row is exhaustive: only string items and object items
// are supported. Checked here (not just inside `schemaToZod`) so an
// unsupported item type — say, an array of integers — renders the disabled
// fallback instead of `ArrayWidget` silently treating every row as a plain
// text input.
function isSupportedArray(
  schema: JsonSchema,
  defs: Record<string, JsonSchema>,
  depth: number,
): boolean {
  if (!schema.items) {
    return false;
  }
  const { schema: itemSchema } = resolveSchema(schema.items, defs);
  if (itemSchema.type === 'string') {
    return true;
  }
  return (
    itemSchema.type === 'object' && Boolean(itemSchema.properties) && depth < MAX_NESTING_DEPTH
  );
}

function renderControl(params: {
  name: string;
  schema: JsonSchema;
  defs: Record<string, JsonSchema>;
  depth: number;
  required: boolean;
  disabled: boolean;
  describedBy?: string;
  invalid: boolean;
}): ReactNode {
  const { name, schema, defs, depth, required, disabled, describedBy, invalid } = params;

  if (schema['x-secret']) {
    return (
      <SecretWidget name={name} disabled={disabled} describedBy={describedBy} invalid={invalid} />
    );
  }
  switch (schema.type) {
    case 'string':
      return schema.enum ? (
        <EnumWidget
          name={name}
          options={schema.enum as string[]}
          disabled={disabled}
          required={required}
          describedBy={describedBy}
          invalid={invalid}
        />
      ) : (
        <StringWidget
          name={name}
          schema={schema}
          disabled={disabled}
          required={required}
          describedBy={describedBy}
          invalid={invalid}
        />
      );
    case 'integer':
      return (
        <NumberWidget
          name={name}
          integer
          disabled={disabled}
          required={required}
          describedBy={describedBy}
          invalid={invalid}
        />
      );
    case 'number':
      return (
        <NumberWidget
          name={name}
          integer={false}
          disabled={disabled}
          required={required}
          describedBy={describedBy}
          invalid={invalid}
        />
      );
    case 'boolean':
      return <BooleanWidget name={name} disabled={disabled} describedBy={describedBy} />;
    case 'array':
      return isSupportedArray(schema, defs, depth) ? (
        <ArrayWidget
          name={name}
          // Non-null: isSupportedArray already checked schema.items exists.
          itemSchema={schema.items as JsonSchema}
          defs={defs}
          depth={depth}
          disabled={disabled}
        />
      ) : (
        <FallbackWidget name={name} />
      );
    case 'object':
      return schema.properties && depth < MAX_NESTING_DEPTH ? (
        <ObjectWidget name={name} schema={schema} defs={defs} depth={depth} disabled={disabled} />
      ) : (
        <FallbackWidget name={name} />
      );
    default:
      return <FallbackWidget name={name} />;
  }
}

function FieldShell(props: {
  name: string;
  label: string;
  description?: string;
  error?: string;
  required: boolean;
  children: ReactNode;
}): ReactElement {
  const { name, label, description, error, required, children } = props;
  const descriptionId = description ? `${name}-description` : undefined;
  const errorId = error ? `${name}-error` : undefined;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={name} className="text-text text-sm font-medium">
        {label}
        {required && (
          <span className="text-danger" aria-hidden="true">
            {' '}
            *
          </span>
        )}
      </label>
      {description && (
        <p id={descriptionId} className="text-text-muted text-xs">
          {description}
        </p>
      )}
      {children}
      {error && (
        <p id={errorId} role="alert" className="text-danger text-xs">
          {error}
        </p>
      )}
    </div>
  );
}
