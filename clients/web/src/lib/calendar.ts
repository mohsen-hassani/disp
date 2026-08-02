/**
 * Month-grid maths for the plant care calendar.
 *
 * Everything here works in UTC (`Date.UTC`, `toISOString`) and passes
 * `timeZone: 'UTC'` to every formatter. Calendar days are whole days, not
 * instants: building them from local-time `Date`s makes the 1st of the month
 * land on the previous day for anyone west of UTC, which silently shifts the
 * whole grid. The API speaks plain `YYYY-MM-DD` for the same reason.
 */

const DAYS_IN_GRID = 42; // 6 weeks — the most any month can span
const MS_PER_DAY = 86_400_000;

const monthFormatter = new Intl.DateTimeFormat(undefined, {
  month: 'long',
  year: 'numeric',
  timeZone: 'UTC',
});
const weekdayFormatter = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  timeZone: 'UTC',
});
const dayFormatter = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC',
});

export interface GridDay {
  /** `YYYY-MM-DD`, matching the API's day keys exactly. */
  day: string;
  dayOfMonth: number;
  inMonth: boolean;
  isToday: boolean;
}

function utcDate(day: string): Date {
  const [year, month, date] = day.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, date));
}

function toDayString(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** Today as `YYYY-MM-DD` in the *viewer's* timezone — the day they'd call "today". */
export function todayDay(): string {
  const now = new Date();
  return toDayString(new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())));
}

export function currentMonth(): string {
  return todayDay().slice(0, 7);
}

/** `2026-03` → `2026-02` at delta -1, `2026-04` at +1. Rolls the year over. */
export function shiftMonth(month: string, delta: number): string {
  const [year, monthNumber] = month.split('-').map(Number);
  const shifted = new Date(Date.UTC(year, monthNumber - 1 + delta, 1));
  return toDayString(shifted).slice(0, 7);
}

/** `2026-03` → "March 2026". */
export function monthLabel(month: string): string {
  return monthFormatter.format(utcDate(`${month}-01`));
}

/** `2026-03-18` → "18 Mar" (order and separator follow the viewer's locale). */
export function dayLabel(day: string): string {
  return dayFormatter.format(utcDate(day));
}

/**
 * Weekday headers starting on Monday. 2024-01-01 was a Monday, so it seeds
 * seven consecutive days in the right order for any locale.
 */
export function weekdayLabels(): string[] {
  return Array.from({ length: 7 }, (_, index) =>
    weekdayFormatter.format(new Date(Date.UTC(2024, 0, 1 + index))),
  );
}

/**
 * The 6×7 grid for one month, padded with the trailing days of the previous
 * month and the leading days of the next so every row is full.
 */
export function buildMonthGrid(month: string, today: string = todayDay()): GridDay[] {
  const first = utcDate(`${month}-01`);
  // getUTCDay() is 0=Sunday; shift so Monday is 0.
  const leading = (first.getUTCDay() + 6) % 7;
  const start = new Date(first.getTime() - leading * MS_PER_DAY);

  return Array.from({ length: DAYS_IN_GRID }, (_, index) => {
    const date = new Date(start.getTime() + index * MS_PER_DAY);
    const day = toDayString(date);
    return {
      day,
      dayOfMonth: date.getUTCDate(),
      inMonth: day.startsWith(month),
      isToday: day === today,
    };
  });
}

/** Groups the API's flat entry list by day, ready for per-cell rendering. */
export function groupByDay<T extends { day: string }>(entries: readonly T[]): Map<string, T[]> {
  const grouped = new Map<string, T[]>();
  for (const entry of entries) {
    const existing = grouped.get(entry.day);
    if (existing) {
      existing.push(entry);
    } else {
      grouped.set(entry.day, [entry]);
    }
  }
  return grouped;
}
