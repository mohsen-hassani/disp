import { describe, expect, it } from 'vitest';

import { schemaToZod } from '../../../src/components/schema-form/schemaToZod';
import type { JsonSchema } from '../../../src/components/schema-form/types';

describe('schemaToZod', () => {
  it('validates required string/integer/boolean/enum fields', () => {
    const schema: JsonSchema = {
      type: 'object',
      required: ['name', 'age'],
      properties: {
        name: { type: 'string', minLength: 1 },
        age: { type: 'integer', minimum: 0 },
        active: { type: 'boolean' },
        color: { type: 'string', enum: ['red', 'green'] },
      },
    };
    const zodSchema = schemaToZod(schema);

    expect(zodSchema.safeParse({ name: '', age: 1 }).success).toBe(false);
    expect(zodSchema.safeParse({ age: -1 }).success).toBe(false);
    expect(zodSchema.safeParse({ name: 'Ada', age: 1, color: 'purple' }).success).toBe(false);
    expect(zodSchema.safeParse({ name: 'Ada', age: 1, active: true, color: 'red' }).success).toBe(
      true,
    );
  });

  it('resolves $ref and treats anyOf[X, null] as nullable+optional', () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: {
        note: { anyOf: [{ $ref: '#/$defs/Note' }, { type: 'null' }] },
      },
    };
    const defs = { Note: { type: 'string' } };
    const zodSchema = schemaToZod(schema, defs);

    expect(zodSchema.safeParse({}).success).toBe(true);
    expect(zodSchema.safeParse({ note: null }).success).toBe(true);
    expect(zodSchema.safeParse({ note: 'hello' }).success).toBe(true);
  });

  it('falls back to unknown for an array whose items are neither string nor object', () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: { weird: { type: 'array', items: { type: 'integer' } } },
    };
    const zodSchema = schemaToZod(schema);
    // z.unknown() accepts anything — the point is it doesn't throw building the schema.
    expect(zodSchema.safeParse({ weird: [1, 2, 3] }).success).toBe(true);
  });

  it('falls back to unknown past the three-level nesting cap', () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: {
        a: {
          type: 'object',
          properties: {
            b: {
              type: 'object',
              properties: {
                c: { type: 'object', properties: { d: { type: 'string' } } },
              },
            },
          },
        },
      },
    };
    const zodSchema = schemaToZod(schema);
    // Whatever shape "d" ends up as, this must not throw while building or parsing.
    expect(() => zodSchema.safeParse({ a: { b: { c: { d: 'anything' } } } })).not.toThrow();
  });
});
