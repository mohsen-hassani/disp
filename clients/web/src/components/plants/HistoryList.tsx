import { useQuery } from '@tanstack/react-query';
import type { ReactElement } from 'react';

import { plantHistoryQueryOptions } from '../../api/queries';
import { dateOnly } from '../../lib/format';

interface HistoryListProps {
  plantId: string;
}

/** M14 §5's "recent history" — `CareLogOut`: action, due date, completion date, how late (or early). */
export function HistoryList({ plantId }: HistoryListProps): ReactElement | null {
  const historyQuery = useQuery(plantHistoryQueryOptions(plantId));

  if (historyQuery.isPending) {
    return (
      <section>
        <h2 className="text-text mb-2 text-sm font-medium">History</h2>
        <p aria-busy="true" className="text-text-muted text-sm">
          Loading…
        </p>
      </section>
    );
  }

  if (historyQuery.isError) {
    return (
      <section>
        <h2 className="text-text mb-2 text-sm font-medium">History</h2>
        <p role="alert" className="text-text-muted text-sm">
          Failed to load history.
        </p>
      </section>
    );
  }

  const logs = historyQuery.data ?? [];

  return (
    <section>
      <h2 className="text-text mb-2 text-sm font-medium">History</h2>
      {logs.length === 0 ? (
        <p className="text-text-muted text-sm italic">No care logged yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {logs.map((log) => (
            <li key={log.id} className="border-border bg-surface rounded-md border p-3">
              <p className="text-text text-sm font-medium">{log.action_name}</p>
              <p className="text-text-muted text-xs">
                Done {dateOnly(log.completed_on)} · due {dateOnly(log.due_on)}
                {log.days_late > 0
                  ? ` · ${log.days_late} ${log.days_late === 1 ? 'day' : 'days'} late`
                  : log.days_late < 0
                    ? ` · ${-log.days_late} ${-log.days_late === 1 ? 'day' : 'days'} early`
                    : ' · on time'}
              </p>
              {log.note && <p className="text-text mt-1 text-sm whitespace-pre-wrap">{log.note}</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
