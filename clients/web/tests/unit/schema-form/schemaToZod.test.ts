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

  it('falls back to unknown for a non-string x-secret field (a masked dict, not a masked scalar)', () => {
    // Confirmed against a live `core.notifier` manifest: `urls: dict[str,
    // str]` with `x-secret: true` has no `properties` key at all (it's a
    // free-form map via `additionalProperties`), and the server masks it
    // per-entry (`{key: "***", ...}`), not as a single "***" scalar.
    // Appendix B's only `x-secret` row is `{"type":"string","x-secret":
    // true}` — this must not be treated as a maskable string.
    const schema: JsonSchema = {
      type: 'object',
      properties: {
        // No `properties` key — a free-form map, not a fixed-shape object.
        urls: { type: 'object', 'x-secret': true },
      },
    };
    const zodSchema = schemaToZod(schema);
    expect(zodSchema.safeParse({ urls: { a: '***', b: '***' } }).success).toBe(true);
    expect(zodSchema.safeParse({}).success).toBe(true);
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

  it('validates an array of strings, honoring minItems/maxItems', () => {
    const schema: JsonSchema = {
      type: 'object',
      required: ['tags'],
      properties: { tags: { type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 2 } },
    };
    const zodSchema = schemaToZod(schema);

    expect(zodSchema.safeParse({ tags: [] }).success).toBe(false);
    expect(zodSchema.safeParse({ tags: ['a', 'b', 'c'] }).success).toBe(false);
    expect(zodSchema.safeParse({ tags: ['a'] }).success).toBe(true);
  });

  it('validates an array of objects, and makes it optional when not required', () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: {
        rows: {
          type: 'array',
          items: { type: 'object', properties: { label: { type: 'string' } } },
        },
      },
    };
    const zodSchema = schemaToZod(schema);

    expect(zodSchema.safeParse({}).success).toBe(true);
    expect(zodSchema.safeParse({ rows: [{ label: 'x' }] }).success).toBe(true);
    expect(zodSchema.safeParse({ rows: [{ label: 5 }] }).success).toBe(false);
  });

  it('falls back to unknown for an array with no items schema at all', () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: { anything: { type: 'array' } },
    };
    const zodSchema = schemaToZod(schema);
    expect(zodSchema.safeParse({ anything: [1, 'two', {}] }).success).toBe(true);
  });

  it('validates string format/pattern/maxLength constraints', () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: {
        email: { type: 'string', format: 'email' },
        site: { type: 'string', format: 'uri' },
        when: { type: 'string', format: 'date-time' },
        code: { type: 'string', pattern: '^[A-Z]{3}$' },
        bio: { type: 'string', maxLength: 10 },
      },
    };
    const zodSchema = schemaToZod(schema);

    expect(zodSchema.safeParse({ email: 'not-an-email' }).success).toBe(false);
    expect(zodSchema.safeParse({ email: 'a@b.com' }).success).toBe(true);
    expect(zodSchema.safeParse({ site: 'not a url' }).success).toBe(false);
    expect(zodSchema.safeParse({ site: 'https://example.com' }).success).toBe(true);
    expect(zodSchema.safeParse({ when: 'not-a-date' }).success).toBe(false);
    expect(zodSchema.safeParse({ when: '2026-01-01T00:00:00Z' }).success).toBe(true);
    expect(zodSchema.safeParse({ code: 'abc' }).success).toBe(false);
    expect(zodSchema.safeParse({ code: 'ABC' }).success).toBe(true);
    expect(zodSchema.safeParse({ bio: 'x'.repeat(11) }).success).toBe(false);
  });

  it('validates number maximum and treats a blank/NaN input as absent', () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: { score: { type: 'number', maximum: 5 } },
    };
    const zodSchema = schemaToZod(schema);

    expect(zodSchema.safeParse({ score: 6 }).success).toBe(false);
    expect(zodSchema.safeParse({ score: NaN }).success).toBe(true);
    expect(zodSchema.safeParse({ score: '' }).success).toBe(true);
  });

  it('makes a required boolean mandatory and an optional one, optional', () => {
    const required: JsonSchema = {
      type: 'object',
      required: ['active'],
      properties: { active: { type: 'boolean' } },
    };
    expect(schemaToZod(required).safeParse({}).success).toBe(false);

    const optional: JsonSchema = { type: 'object', properties: { active: { type: 'boolean' } } };
    expect(schemaToZod(optional).safeParse({}).success).toBe(true);
  });

  it('treats a string x-secret field as nullable/optional, accepting null (Clear) and omission', () => {
    const schema: JsonSchema = {
      type: 'object',
      required: ['token'],
      properties: { token: { type: 'string', 'x-secret': true } },
    };
    const zodSchema = schemaToZod(schema);

    expect(zodSchema.safeParse({}).success).toBe(true);
    expect(zodSchema.safeParse({ token: null }).success).toBe(true);
    expect(zodSchema.safeParse({ token: 'new-secret' }).success).toBe(true);
  });

  it('falls back to unknown for an object past the nesting cap even when required', () => {
    const schema: JsonSchema = {
      type: 'object',
      required: ['a'],
      properties: {
        a: {
          type: 'object',
          required: ['b'],
          properties: {
            b: {
              type: 'object',
              properties: { c: { type: 'object', properties: { d: { type: 'string' } } } },
            },
          },
        },
      },
    };
    const zodSchema = schemaToZod(schema);
    expect(zodSchema.safeParse({ a: { b: { anything: 'goes' } } }).success).toBe(true);
  });
});
