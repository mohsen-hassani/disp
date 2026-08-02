import { describe, expect, it } from 'vitest';

import { describeDue, describeNextDue, dueTone } from '../../../src/components/plants/dueText';

describe('dueTone', () => {
  it('separates behind, due today, and not yet due', () => {
    expect(dueTone(3)).toBe('overdue');
    expect(dueTone(1)).toBe('overdue');
    expect(dueTone(0)).toBe('today');
    expect(dueTone(-1)).toBe('upcoming');
  });
});

describe('describeDue', () => {
  it('matches the backend tile wording for lateness', () => {
    expect(describeDue(1, '2026-03-01')).toBe('1 day behind');
    expect(describeDue(2, '2026-03-01')).toBe('2 days behind');
  });

  it('names today and tomorrow rather than printing a date', () => {
    expect(describeDue(0, '2026-03-01')).toBe('Due today');
    expect(describeDue(-1, '2026-03-02')).toBe('Due tomorrow');
  });

  it('falls back to a date further out', () => {
    expect(describeDue(-9, '2026-03-18')).toMatch(/18/);
  });
});

describe('describeNextDue', () => {
  it('reads as a next occurrence, not a warning', () => {
    expect(describeNextDue('2026-03-18')).toMatch(/^Next /);
  });
});
