// WEB-SPEC Appendix B's exhaustive subset of Pydantic-generated JSON Schema
// — anything outside this shape renders as the disabled fallback (§14.3
// rule 5), not a crash. `$defs` lives only on the root schema (Pydantic
// never nests `$defs` inside a `$ref` target), so it's threaded through
// `resolveSchema` as a separate argument rather than a property every
// nested schema would otherwise need to repeat.
export interface JsonSchema {
  type?: string;
  format?: string;
  enum?: unknown[];
  items?: JsonSchema;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  title?: string;
  description?: string;
  default?: unknown;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  minimum?: number;
  maximum?: number;
  minItems?: number;
  maxItems?: number;
  anyOf?: JsonSchema[];
  $ref?: string;
  'x-secret'?: boolean;
}

export interface JsonSchemaDoc extends JsonSchema {
  $defs?: Record<string, JsonSchema>;
}

const REF_PREFIX = '#/$defs/';

/** Resolves `$ref` and unwraps the `anyOf: [X, {type: "null"}]` optional-field pattern. */
export function resolveSchema(
  schema: JsonSchema,
  defs: Record<string, JsonSchema>,
): { schema: JsonSchema; nullable: boolean } {
  if (schema.$ref?.startsWith(REF_PREFIX)) {
    const target = defs[schema.$ref.slice(REF_PREFIX.length)];
    return target ? resolveSchema(target, defs) : { schema, nullable: false };
  }
  if (schema.anyOf?.length === 2) {
    const nullBranch = schema.anyOf.find((branch) => branch.type === 'null');
    const otherBranch = schema.anyOf.find((branch) => branch.type !== 'null');
    if (nullBranch && otherBranch) {
      const resolved = resolveSchema(otherBranch, defs);
      return {
        schema: { ...resolved.schema, title: schema.title ?? resolved.schema.title },
        nullable: true,
      };
    }
  }
  return { schema, nullable: false };
}
