// Pure date-grid math for the `/plants/calendar` screen (M14 §5) — kept
// framework-free so it's directly unit-testable without mounting anything.
// All arithmetic is done with local-time `Date` parts (never `new
// Date(isoString)` on a date-only string), for the same reason `dateOnly`
// in `lib/format.ts` does: parsing a plain `YYYY-MM-DD` as UTC and then
// formatting in the caller's local timezone can roll the day backward.

const MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;

export function isValidMonth(month: string): boolean {
  return MONTH_RE.test(month);
}

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

export function formatMonth(year: number, month: number): string {
  return `${year}-${pad2(month)}`;
}

function formatDate(year: number, month: number, day: number): string {
  return `${year}-${pad2(month)}-${pad2(day)}`;
}

export function currentMonth(): string {
  const now = new Date();
  return formatMonth(now.getFullYear(), now.getMonth() + 1);
}

function parseMonth(month: string): { year: number; month: number } {
  const [year, monthNum] = month.split('-').map(Number);
  return { year: year ?? 0, month: monthNum ?? 1 };
}

export function shiftMonth(month: string, delta: number): string {
  const { year, month: m } = parseMonth(month);
  const shifted = new Date(year, m - 1 + delta, 1);
  return formatMonth(shifted.getFullYear(), shifted.getMonth() + 1);
}

const monthLabelFormatter = new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'long' });

export function monthLabel(month: string): string {
  const { year, month: m } = parseMonth(month);
  return monthLabelFormatter.format(new Date(year, m - 1, 1));
}

export interface CalendarDay {
  date: string;
  inMonth: boolean;
}

/** A fixed 6-row, Sunday-start grid (42 cells) so the layout never reflows between months. */
export function buildCalendarWeeks(month: string): CalendarDay[][] {
  const { year, month: m } = parseMonth(month);
  const firstOfMonth = new Date(year, m - 1, 1);
  const startWeekday = firstOfMonth.getDay();
  const gridStart = new Date(year, m - 1, 1 - startWeekday);

  const weeks: CalendarDay[][] = [];
  for (let week = 0; week < 6; week++) {
    const days: CalendarDay[] = [];
    for (let day = 0; day < 7; day++) {
      const cellDate = new Date(gridStart);
      cellDate.setDate(gridStart.getDate() + week * 7 + day);
      days.push({
        date: formatDate(cellDate.getFullYear(), cellDate.getMonth() + 1, cellDate.getDate()),
        inMonth: cellDate.getMonth() === m - 1,
      });
    }
    weeks.push(days);
  }
  return weeks;
}
