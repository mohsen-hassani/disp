import { AlertTriangle, CheckCircle2, Clock } from 'lucide-react';
import type { ReactElement, ReactNode } from 'react';

import { dateOnly } from '../../lib/format';

type BadgeTone = 'danger' | 'warning' | 'neutral';

const TONE_CLASSES: Record<BadgeTone, string> = {
  danger: 'bg-danger/10 text-danger',
  warning: 'bg-warning/10 text-warning',
  neutral: 'bg-surface-sunken text-text-muted',
};

const baseClass = 'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium';

// §21 A8: overdue state is never signalled by colour alone — every tone
// pairs a distinct icon with distinct text, so it still reads correctly for
// a colour-blind user or in a screen reader.
function Badge({
  tone,
  icon: Icon,
  children,
}: {
  tone: BadgeTone;
  icon: typeof AlertTriangle;
  children: ReactNode;
}): ReactElement {
  return (
    <span className={`${baseClass} ${TONE_CLASSES[tone]}`}>
      <Icon className="h-3 w-3" aria-hidden="true" />
      {children}
    </span>
  );
}

interface PlantDueBadgeProps {
  dueCount: number;
  maxDaysOverdue: number;
  nextDueOn: string | null;
}

/** M14 §5's list/detail-header badge, derived from `PlantOut`'s rollups — never a per-row round trip. */
export function PlantDueBadge({
  dueCount,
  maxDaysOverdue,
  nextDueOn,
}: PlantDueBadgeProps): ReactElement {
  if (maxDaysOverdue > 0) {
    const days = maxDaysOverdue === 1 ? 'day' : 'days';
    return (
      <Badge tone="danger" icon={AlertTriangle}>
        Up to {maxDaysOverdue} {days} overdue
      </Badge>
    );
  }
  if (dueCount > 0) {
    return (
      <Badge tone="warning" icon={Clock}>
        Due today
      </Badge>
    );
  }
  if (nextDueOn) {
    return (
      <Badge tone="neutral" icon={CheckCircle2}>
        Next due {dateOnly(nextDueOn)}
      </Badge>
    );
  }
  return (
    <Badge tone="neutral" icon={CheckCircle2}>
      No care scheduled
    </Badge>
  );
}

interface IntervalDueBadgeProps {
  daysOverdue: number;
  nextDueOn: string;
}

/** M14 §5's per-interval badge on the detail screen, derived from `CareIntervalOut.days_overdue` (negative = not yet due). */
export function IntervalDueBadge({ daysOverdue, nextDueOn }: IntervalDueBadgeProps): ReactElement {
  if (daysOverdue > 0) {
    const days = daysOverdue === 1 ? 'day' : 'days';
    return (
      <Badge tone="danger" icon={AlertTriangle}>
        {daysOverdue} {days} overdue
      </Badge>
    );
  }
  if (daysOverdue === 0) {
    return (
      <Badge tone="warning" icon={Clock}>
        Due today
      </Badge>
    );
  }
  return (
    <Badge tone="neutral" icon={CheckCircle2}>
      Due {dateOnly(nextDueOn)}
    </Badge>
  );
}
