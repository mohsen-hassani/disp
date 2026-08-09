// WEB-SPEC §7.2. Mirrors the backend's ProblemDetail response shape
// (src/disp/core/errors.py) so 4xx/5xx bodies can be mapped to UI behavior
// per §7.3's table (documented in full in src/api/client.ts's neighbor,
// M03/M06-M08's screens).
export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  code: string;
  request_id: string;
  errors?: Array<{ loc: (string | number)[]; msg: string; type: string }>;
}

function isString(value: unknown): value is string {
  return typeof value === 'string';
}

export function isProblem(value: unknown): value is ProblemDetail {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    isString(candidate.type) &&
    isString(candidate.title) &&
    typeof candidate.status === 'number' &&
    isString(candidate.detail) &&
    isString(candidate.instance) &&
    isString(candidate.code) &&
    isString(candidate.request_id)
  );
}

/**
 * Tolerates a non-conforming body (an HTML error page from a misconfigured
 * proxy, an empty body) and synthesizes a fallback rather than throwing —
 * this must never be the thing that crashes the error-handling path itself.
 */
export function parseProblem(res: Response, body: unknown): ProblemDetail {
  if (isProblem(body)) {
    return body;
  }
  return {
    type: 'about:blank',
    title: 'Something went wrong',
    status: res.status,
    detail: 'The server returned an unexpected response.',
    instance: res.url,
    code: 'core.platform.internal_error',
    request_id: '',
  };
}
