import { describe, expect, it } from 'vitest';

import type { ProblemDetail } from '../../../src/api/problem';
import { describeSettingsError, filterDirtyValues } from '../../../src/api/queries';

function makeProblem(overrides: Partial<ProblemDetail> = {}): ProblemDetail {
  return {
    type: 'about:blank',
    title: 'Error',
    status: 500,
    detail: 'Something broke',
    instance: '/api/settings/core',
    code: 'core.platform.internal_error',
    request_id: 'req-1',
    ...overrides,
  };
}

describe('filterDirtyValues', () => {
  it('keeps only keys marked dirty by react-hook-form', () => {
    const values = { name: 'Ada', age: 30, active: true };
    const dirtyFields = { name: true };
    expect(filterDirtyValues(values, dirtyFields)).toEqual({ name: 'Ada' });
  });

  it('returns an empty object when nothing is dirty', () => {
    expect(filterDirtyValues({ name: 'Ada' }, {})).toEqual({});
  });

  it('includes an array/object-valued key whose nested dirty marker is truthy', () => {
    // react-hook-form marks nested dirtiness with a structural mirror
    // (e.g. `{ channels: [{ label: true }] }`), not a plain boolean — any
    // truthy value at the top-level key means "this field changed."
    const values = { channels: [{ id: 'email', label: 'Email Updated' }] };
    const dirtyFields = { channels: [{ label: true }] };
    expect(filterDirtyValues(values, dirtyFields)).toEqual({
      channels: [{ id: 'email', label: 'Email Updated' }],
    });
  });
});

// §14.5.
describe('describeSettingsError', () => {
  it('uses the distinct decryption-failed copy, not a generic 5xx toast', () => {
    const message = describeSettingsError(makeProblem({ code: 'core.settings.decryption_failed' }));
    expect(message).toMatch(/encryption key may have changed/i);
  });

  it('maps a 403 to the generic permission-denied copy', () => {
    expect(describeSettingsError(makeProblem({ status: 403 }))).toBe(
      "You don't have permission to do that.",
    );
  });

  it('includes the request_id for other 5xx errors', () => {
    expect(describeSettingsError(makeProblem({ status: 500, request_id: 'req-xyz' }))).toContain(
      'req-xyz',
    );
  });

  it('falls back to the problem detail for other statuses', () => {
    expect(describeSettingsError(makeProblem({ status: 409, detail: 'Conflict.' }))).toBe(
      'Conflict.',
    );
  });
});
