import { describe, expect, it } from 'vitest';

import {
  buildCalendarWeeks,
  currentMonth,
  isValidMonth,
  monthLabel,
  shiftMonth,
} from '../../../src/components/plants/calendarMonth';

describe('isValidMonth', () => {
  it.each(['2026-01', '2026-12', '2026-08'])('accepts %s', (month) => {
    expect(isValidMonth(month)).toBe(true);
  });

  it.each(['2026-13', '2026-00', '2026-1', '26-01', 'not-a-month', ''])('rejects %s', (month) => {
    expect(isValidMonth(month)).toBe(false);
  });
});

describe('shiftMonth', () => {
  it('moves forward within a year', () => {
    expect(shiftMonth('2026-08', 1)).toBe('2026-09');
  });

  it('moves backward within a year', () => {
    expect(shiftMonth('2026-08', -1)).toBe('2026-07');
  });

  it('rolls over to the next year', () => {
    expect(shiftMonth('2026-12', 1)).toBe('2027-01');
  });

  it('rolls back to the previous year', () => {
    expect(shiftMonth('2026-01', -1)).toBe('2025-12');
  });
});

describe('monthLabel', () => {
  it('renders a human-readable month and year', () => {
    expect(monthLabel('2026-08')).toBe('August 2026');
  });
});

describe('currentMonth', () => {
  it('formats as YYYY-MM', () => {
    expect(currentMonth()).toMatch(/^\d{4}-\d{2}$/);
  });
});

describe('buildCalendarWeeks', () => {
  it('returns a fixed 6-row, 7-column grid', () => {
    const weeks = buildCalendarWeeks('2026-08');
    expect(weeks).toHaveLength(6);
    for (const week of weeks) {
      expect(week).toHaveLength(7);
    }
  });

  it('includes every day of the month exactly once, marked in-month', () => {
    const weeks = buildCalendarWeeks('2026-08');
    const inMonthDays = weeks.flat().filter((day) => day.inMonth);
    // August 2026 has 31 days.
    expect(inMonthDays).toHaveLength(31);
    expect(inMonthDays[0]?.date).toBe('2026-08-01');
    expect(inMonthDays.at(-1)?.date).toBe('2026-08-31');
  });

  it('fills leading/trailing cells from adjacent months, marked out-of-month', () => {
    const weeks = buildCalendarWeeks('2026-08');
    const firstCell = weeks[0]?.[0];
    // 2026-08-01 is a Saturday, so the grid's first cell is a trailing July day.
    expect(firstCell?.inMonth).toBe(false);
    expect(firstCell?.date.startsWith('2026-07')).toBe(true);
  });
});
