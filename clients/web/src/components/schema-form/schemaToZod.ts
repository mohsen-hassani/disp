import { z, type ZodTypeAny } from 'zod';

import { type JsonSchema, resolveSchema } from './types';

// Appendix B: "Nesting deeper than three levels renders the fallback — the
// backend is not expected to emit it." depth=1 is the form's own top-level
// object; each nested object/array-of-object adds one.
const MAX_NESTING_DEPTH = 3;

// Every native form control that can be "empty" (a blank text input, an
// unselected <select>, a number input with nothing typed) produces "" or
// NaN — never `undefined`. Without normalizing first, two bugs happen at
// once: an *optional* field left blank still fails whatever base validator
// runs (an enum has no option matching ""), and a *required* field with no
// `minLength` of its own silently accepts "" as if it were a real value.
// Zod's own `.optional()` can't fix this by itself — it only short-circuits
// on a literal `undefined` input, which "" never is until this preprocess
// step turns it into one.
function normalizeEmpty(value: unknown): unknown {
  if (value === '') {
    return undefined;
  }
  if (typeof value === 'number' && Number.isNaN(value)) {
    return undefined;
  }
  return value;
}

// The disabled-fallback field (§14.3 rule 5) never calls `register()` — its
// key is genuinely *absent* from the submitted values, not just
// `undefined`. Zod v4's `z.object()` distinguishes the two (an absent key
// fails even against `z.unknown()`), so every fallback path must be
// `.optional()` explicitly, regardless of `required` — enforcing
// "required" against a field the user has no way to fill in would make
// the form permanently unsubmittable.
function fallbackZod(): ZodTypeAny {
  return z.unknown().optional();
}

function stringZod(schema: JsonSchema): ZodTypeAny {
  let base = z.string();
  if (schema.minLength !== undefined) {
    base = base.min(schema.minLength);
  }
  if (schema.maxLength !== undefined) {
    base = base.max(schema.maxLength);
  }
  if (schema.pattern) {
    base = base.regex(new RegExp(schema.pattern));
  }
  if (schema.format === 'email') {
    return base.email();
  }
  if (schema.format === 'uri') {
    return base.url();
  }
  if (schema.format === 'date-time') {
    return base.datetime();
  }
  return base;
}

function numberZod(schema: JsonSchema, integer: boolean): ZodTypeAny {
  let base = integer ? z.number().int() : z.number();
  if (schema.minimum !== undefined) {
    base = base.min(schema.minimum);
  }
  if (schema.maximum !== undefined) {
    base = base.max(schema.maximum);
  }
  return base;
}

// string/enum/integer/number are exactly the types whose native control can
// produce "". `required` is applied *inside* the preprocess step (not via
// an external `.optional()` wrap after the fact) so it sees the normalized
// value, not the raw "".
function leafZod(schema: JsonSchema, required: boolean): ZodTypeAny {
  const base =
    schema.type === 'string'
      ? schema.enum
        ? z.enum(schema.enum as [string, ...string[]])
        : stringZod(schema)
      : numberZod(schema, schema.type === 'integer');
  return z.preprocess(normalizeEmpty, required ? base : base.optional());
}

function objectZod(
  schema: JsonSchema,
  defs: Record<string, JsonSchema>,
  depth: number,
): ZodTypeAny {
  const required = new Set(schema.required ?? []);
  const shape: Record<string, ZodTypeAny> = {};
  for (const [key, propSchema] of Object.entries(schema.properties ?? {})) {
    shape[key] = fieldZod(propSchema, defs, depth, required.has(key));
  }
  return z.object(shape);
}

function arrayZod(
  schema: JsonSchema,
  defs: Record<string, JsonSchema>,
  depth: number,
  required: boolean,
): ZodTypeAny {
  if (!schema.items) {
    return fallbackZod();
  }
  const { schema: itemSchema } = resolveSchema(schema.items, defs);
  let base: z.ZodArray<ZodTypeAny>;
  if (itemSchema.type === 'string') {
    base = z.array(z.string());
  } else if (itemSchema.type === 'object' && itemSchema.properties && depth < MAX_NESTING_DEPTH) {
    base = z.array(objectZod(itemSchema, defs, depth + 1));
  } else {
    // Only string and object items are in Appendix B's exhaustive table.
    return fallbackZod();
  }
  if (schema.minItems !== undefined) {
    base = base.min(schema.minItems);
  }
  if (schema.maxItems !== undefined) {
    base = base.max(schema.maxItems);
  }
  return required ? base : base.optional();
}

function baseZod(
  schema: JsonSchema,
  defs: Record<string, JsonSchema>,
  depth: number,
  required: boolean,
): ZodTypeAny {
  if (schema['x-secret']) {
    // §14.4: an untouched secret is omitted from the payload entirely, and
    // the masked "***" sentinel is never a real value the client sends —
    // always optional client-side regardless of `required`, since a
    // secret already set server-side shouldn't force a re-type just to
    // pass validation. `.nullable()` because the Clear button explicitly
    // sends `null` for the key.
    return z.string().nullable().optional();
  }
  switch (schema.type) {
    case 'string':
    case 'integer':
    case 'number':
      return leafZod(schema, required);
    case 'boolean':
      // No empty-string representation — a Switch is always true or false.
      return required ? z.boolean() : z.boolean().optional();
    case 'array':
      return arrayZod(schema, defs, depth, required);
    case 'object': {
      if (!schema.properties || depth >= MAX_NESTING_DEPTH) {
        return fallbackZod();
      }
      const objType = objectZod(schema, defs, depth + 1);
      return required ? objType : objType.optional();
    }
    default:
      return fallbackZod();
  }
}

function fieldZod(
  schema: JsonSchema,
  defs: Record<string, JsonSchema>,
  depth: number,
  required: boolean,
): ZodTypeAny {
  const { schema: resolved, nullable } = resolveSchema(schema, defs);
  const zodType = baseZod(resolved, defs, depth, required && !nullable);
  return nullable ? zodType.nullable().optional() : zodType;
}

/** Converts a form's root JSON Schema (always an object) into a Zod schema for client-side validation. */
export function schemaToZod(schema: JsonSchema, defs: Record<string, JsonSchema> = {}): ZodTypeAny {
  return objectZod(schema, defs, 1);
}
