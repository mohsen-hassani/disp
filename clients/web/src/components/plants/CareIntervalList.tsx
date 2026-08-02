import { Check, Trash2 } from 'lucide-react';
import { type ReactElement, useState } from 'react';

import type { CareIntervalOut } from '../../api/generated';
import { todayDay } from '../../lib/calendar';
import { Spinner } from '../feedback/Spinner';
import { useToast } from '../feedback/ToastProvider';
import { TONE_CLASS, describeDue, dueTone } from './dueText';
import { dangerButtonClass, primaryButtonClass, secondaryButtonClass } from './styles';
import { useCompleteInterval, useDeleteInterval } from './usePlantMutations';

interface CareIntervalListProps {
  plantId: string;
  intervals: CareIntervalOut[];
  offline: boolean;
}

/**
 * The schedule. Each row can be marked done, which is the only place the
 * "reschedule from the completion date" rule is exercised from the UI — the
 * server recomputes `next_due_on`, and the whole `plants` query prefix is
 * invalidated so the badge, the calendar and the dashboard tile all follow.
 */
export function CareIntervalList({
  plantId,
  intervals,
  offline,
}: CareIntervalListProps): ReactElement {
  if (intervals.length === 0) {
    return (
      <p className="text-text-muted text-sm">
        No intervals yet. Add one below — for example “Water” every 15 days.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {intervals.map((interval) => (
        <IntervalRow key={interval.id} plantId={plantId} interval={interval} offline={offline} />
      ))}
    </ul>
  );
}

function IntervalRow({
  plantId,
  interval,
  offline,
}: {
  plantId: string;
  interval: CareIntervalOut;
  offline: boolean;
}): ReactElement {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const complete = useCompleteInterval(plantId);
  const remove = useDeleteInterval(plantId);
  const { showToast } = useToast();

  const tone = dueTone(interval.days_overdue);
  const busy = complete.isPending || remove.isPending;

  return (
    <li className="border-border bg-surface flex flex-wrap items-center gap-3 rounded-md border p-3">
      <div className="min-w-0 flex-1">
        <p className="text-text text-sm font-medium">{interval.name}</p>
        <p className="text-text-muted text-xs">
          Every {interval.interval_days} days
          {interval.last_done_on ? ` · last done ${interval.last_done_on}` : ' · never done'}
        </p>
      </div>

      <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${TONE_CLASS[tone]}`}>
        {describeDue(interval.days_overdue, interval.next_due_on)}
      </span>

      {confirmingDelete ? (
        <span className="flex items-center gap-2">
          <span className="text-text-muted text-xs">Delete this interval?</span>
          <button
            type="button"
            className={dangerButtonClass}
            disabled={busy}
            onClick={() =>
              remove.mutate(interval.id, {
                onSuccess: () => showToast(`${interval.name} removed`, 'success'),
                onError: (problem) => showToast(problem.detail, 'error'),
              })
            }
          >
            Delete
          </button>
          <button
            type="button"
            className={secondaryButtonClass}
            onClick={() => setConfirmingDelete(false)}
          >
            Keep
          </button>
        </span>
      ) : (
        <span className="flex items-center gap-2">
          <button
            type="button"
            className={`${primaryButtonClass} inline-flex items-center gap-1.5`}
            disabled={busy || offline}
            title={offline ? 'Unavailable offline' : undefined}
            onClick={() =>
              complete.mutate(
                { intervalId: interval.id, payload: { completed_on: todayDay() } },
                {
                  onSuccess: (result) =>
                    showToast(
                      `${interval.name} done — next on ${result.interval.next_due_on}`,
                      'success',
                    ),
                  onError: (problem) => showToast(problem.detail, 'error'),
                },
              )
            }
          >
            {complete.isPending ? <Spinner /> : <Check className="h-4 w-4" aria-hidden="true" />}
            Mark done
          </button>
          <button
            type="button"
            aria-label={`Delete ${interval.name}`}
            className={secondaryButtonClass}
            disabled={busy || offline}
            onClick={() => setConfirmingDelete(true)}
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </button>
        </span>
      )}
    </li>
  );
}
