import { describe, expect, it } from 'vitest';

import { isProblem, parseProblem, type ProblemDetail } from '../../../src/api/problem';

const VALID_PROBLEM: ProblemDetail = {
  type: 'about:blank',
  title: 'Not found',
  status: 404,
  detail: 'No note with that id.',
  instance: '/api/notes/abc',
  code: 'modules.notes.not_found',
  request_id: 'req-123',
};

describe('isProblem', () => {
  it('accepts a conforming body', () => {
    expect(isProblem(VALID_PROBLEM)).toBe(true);
  });

  it('rejects null, primitives, and shapes missing required fields', () => {
    expect(isProblem(null)).toBe(false);
    expect(isProblem(undefined)).toBe(false);
    expect(isProblem('<html>502 Bad Gateway</html>')).toBe(false);
    expect(isProblem({ ...VALID_PROBLEM, status: '404' })).toBe(false);
    const missingCode: Partial<ProblemDetail> = { ...VALID_PROBLEM };
    delete missingCode.code;
    expect(isProblem(missingCode)).toBe(false);
  });
});

describe('parseProblem', () => {
  it('returns the body unchanged when it already conforms', () => {
    const res = new Response(null, { status: 404 });
    expect(parseProblem(res, VALID_PROBLEM)).toEqual(VALID_PROBLEM);
  });

  it('tolerates a non-conforming body (HTML proxy error page) without throwing', () => {
    const res = new Response(null, { status: 502 });
    const problem = parseProblem(res, '<html><body>502 Bad Gateway</body></html>');
    expect(problem.code).toBe('core.platform.internal_error');
    expect(problem.status).toBe(502);
  });

  it('tolerates an empty body without throwing', () => {
    const res = new Response(null, { status: 500 });
    expect(() => parseProblem(res, undefined)).not.toThrow();
    expect(parseProblem(res, undefined).code).toBe('core.platform.internal_error');
  });
});
