import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildMonthGrid,
  currentMonth,
  dayLabel,
  groupByDay,
  monthLabel,
  shiftMonth,
  todayDay,
  weekdayLabels,
} from '../../../src/lib/calendar';

afterEach(() => {
  vi.useRealTimers();
});

describe('shiftMonth', () => {
  it('moves within a year', () => {
    expect(shiftMonth('2026-03', 1)).toBe('2026-04');
    expect(shiftMonth('2026-03', -1)).toBe('2026-02');
  });

  it('rolls the year over in both directions', () => {
    expect(shiftMonth('2026-12', 1)).toBe('2027-01');
    expect(shiftMonth('2026-01', -1)).toBe('2025-12');
  });
});

describe('buildMonthGrid', () => {
  it('always returns six full weeks', () => {
    expect(buildMonthGrid('2026-03')).toHaveLength(42);
    expect(buildMonthGrid('2026-02')).toHaveLength(42);
  });

  it('starts on the Monday on or before the 1st', () => {
    // 2026-03-01 is a Sunday, so the grid opens on Monday 2026-02-23.
    const grid = buildMonthGrid('2026-03');
    expect(grid[0].day).toBe('2026-02-23');
    expect(grid[0].inMonth).toBe(false);
    expect(grid[6].day).toBe('2026-03-01');
    expect(grid[6].inMonth).toBe(true);
  });

  it('needs no padding when the 1st is itself a Monday', () => {
    // 2026-06-01 is a Monday.
    const grid = buildMonthGrid('2026-06');
    expect(grid[0].day).toBe('2026-06-01');
    expect(grid[0].inMonth).toBe(true);
  });

  it('covers every day of the month exactly once', () => {
    const inMonth = buildMonthGrid('2026-03').filter((cell) => cell.inMonth);
    expect(inMonth).toHaveLength(31);
    expect(new Set(inMonth.map((cell) => cell.day)).size).toBe(31);
  });

  it('handles a leap February', () => {
    const inMonth = buildMonthGrid('2028-02').filter((cell) => cell.inMonth);
    expect(inMonth).toHaveLength(29);
  });

  it('marks exactly one cell as today', () => {
    const grid = buildMonthGrid('2026-03', '2026-03-18');
    expect(grid.filter((cell) => cell.isToday).map((cell) => cell.day)).toEqual(['2026-03-18']);
  });

  it('marks nothing as today in a month that is not the current one', () => {
    expect(buildMonthGrid('2026-03', '2026-09-01').some((cell) => cell.isToday)).toBe(false);
  });
});

describe('todayDay / currentMonth', () => {
  it('reads the viewer’s local date, not the UTC instant', () => {
    // 23:30 on 2026-03-31 local time: a naive toISOString() on the raw Date
    // would report 2026-04-01 for anyone east of UTC, moving the calendar
    // into the wrong month.
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 2, 31, 23, 30, 0));
    expect(todayDay()).toBe('2026-03-31');
    expect(currentMonth()).toBe('2026-03');
  });
});

describe('labels', () => {
  it('formats a month and a day', () => {
    expect(monthLabel('2026-03')).toMatch(/2026/);
    expect(monthLabel('2026-03')).toMatch(/March|Mar/i);
    expect(dayLabel('2026-03-18')).toMatch(/18/);
  });

  it('returns seven weekday labels starting on Monday', () => {
    const labels = weekdayLabels();
    expect(labels).toHaveLength(7);
    expect(new Set(labels).size).toBe(7);
    expect(labels[0]).toMatch(/^M/i);
  });
});

describe('groupByDay', () => {
  it('buckets entries and preserves order within a day', () => {
    const grouped = groupByDay([
      { day: '2026-03-01', id: 'a' },
      { day: '2026-03-02', id: 'b' },
      { day: '2026-03-01', id: 'c' },
    ]);
    expect(grouped.get('2026-03-01')?.map((entry) => entry.id)).toEqual(['a', 'c']);
    expect(grouped.get('2026-03-02')?.map((entry) => entry.id)).toEqual(['b']);
    expect(grouped.get('2026-03-03')).toBeUndefined();
  });
});
