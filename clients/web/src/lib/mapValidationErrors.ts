export interface ServerFieldError {
  loc: Array<string | number>;
  msg: string;
}

// WEB-SPEC §19.3: PLATFORM-SPEC §17.3's `errors: [{loc, msg, type}]`, where
// `loc` is a path like `["body","email"]`. The client drops a leading
// "body"/"query"/"path" segment and joins the remainder with '.' to get the
// react-hook-form field name. A `loc` that isn't one of the caller's known
// fields is reported back unmapped so the caller can surface it at the
// form level instead of silently discarding it.
const LOC_PREFIXES = new Set(['body', 'query', 'path']);

function trimLocPrefix(loc: Array<string | number>): Array<string | number> {
  return loc.length > 0 && typeof loc[0] === 'string' && LOC_PREFIXES.has(loc[0])
    ? loc.slice(1)
    : loc;
}

export interface MappedValidationErrors {
  /** react-hook-form field name -> message, ready for `setError`. */
  fieldErrors: Array<{ field: string; message: string }>;
  /** Errors whose `loc` didn't match any of `knownFields` — render at form level. */
  unmapped: ServerFieldError[];
}

export function mapValidationErrors(
  errors: ServerFieldError[],
  knownFields: ReadonlySet<string>,
): MappedValidationErrors {
  const fieldErrors: Array<{ field: string; message: string }> = [];
  const unmapped: ServerFieldError[] = [];
  for (const serverError of errors) {
    const trimmed = trimLocPrefix(serverError.loc);
    const field = trimmed.join('.');
    if (trimmed.length > 0 && knownFields.has(String(trimmed[0]))) {
      fieldErrors.push({ field, message: serverError.msg });
    } else {
      unmapped.push(serverError);
    }
  }
  return { fieldErrors, unmapped };
}
