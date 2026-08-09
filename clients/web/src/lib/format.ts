const relativeTimeFormatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
});
const dateOnlyFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' });

const DIVISIONS: ReadonlyArray<{ amount: number; unit: Intl.RelativeTimeFormatUnit }> = [
  { amount: 60, unit: 'seconds' },
  { amount: 60, unit: 'minutes' },
  { amount: 24, unit: 'hours' },
  { amount: 7, unit: 'days' },
  { amount: 4.34524, unit: 'weeks' },
  { amount: 12, unit: 'months' },
  { amount: Number.POSITIVE_INFINITY, unit: 'years' },
];

/** "2h ago" / "in 3 days" — used wherever a timestamp needs a relative rendering (§13.5, tile items). */
export function relativeTime(iso: string): string {
  let duration = (new Date(iso).getTime() - Date.now()) / 1000;
  for (const division of DIVISIONS) {
    if (Math.abs(duration) < division.amount) {
      return relativeTimeFormatter.format(Math.round(duration), division.unit);
    }
    duration /= division.amount;
  }
  return relativeTimeFormatter.format(Math.round(duration), 'years');
}

/** The absolute counterpart — goes in a `title` attribute next to `relativeTime`'s text. */
export function dateTime(iso: string): string {
  return dateTimeFormatter.format(new Date(iso));
}

/**
 * For plain `YYYY-MM-DD` dates (plants' `next_due_on`, `due_on`,
 * `completed_on` — no time component). `new Date(iso)` parses those as UTC
 * midnight, so formatting with the caller's local timezone can roll the
 * displayed day backward (a `-05:00` reader would see "the 19th" for a
 * `2026-08-20` due date). Building the `Date` from its parts in local time
 * instead sidesteps that shift entirely.
 */
export function dateOnly(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number);
  return dateOnlyFormatter.format(new Date(year, month - 1, day));
}
