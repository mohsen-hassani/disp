import { dayLabel } from '../../lib/calendar';

export type DueTone = 'overdue' | 'today' | 'upcoming';

/**
 * `days_overdue` from the API is signed: positive is behind, 0 is due today,
 * negative is not yet due. The wording here matches the backend's own tile
 * copy (`describe_lateness`) so the dashboard and this screen never disagree.
 */
export function dueTone(daysOverdue: number): DueTone {
  if (daysOverdue > 0) return 'overdue';
  if (daysOverdue === 0) return 'today';
  return 'upcoming';
}

export function describeDue(daysOverdue: number, nextDueOn: string): string {
  if (daysOverdue > 0) {
    return daysOverdue === 1 ? '1 day behind' : `${daysOverdue} days behind`;
  }
  if (daysOverdue === 0) return 'Due today';
  if (daysOverdue === -1) return 'Due tomorrow';
  return describeNextDue(nextDueOn);
}

/** For a plant with nothing outstanding: just when the next thing lands. */
export function describeNextDue(nextDueOn: string): string {
  return `Next ${dayLabel(nextDueOn)}`;
}

/** Tailwind classes for the badge, keyed by tone. */
export const TONE_CLASS: Record<DueTone, string> = {
  overdue: 'bg-danger text-accent-text',
  today: 'bg-accent text-accent-text',
  upcoming: 'bg-surface-sunken text-text-muted',
};
