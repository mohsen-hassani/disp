import { Link } from '@tanstack/react-router';
import type { ReactElement } from 'react';

import type { CalendarEntry } from '../../api/generated';
import { buildCalendarWeeks } from './calendarMonth';

interface PlantCalendarGridProps {
  month: string;
  entries: CalendarEntry[];
}

const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MAX_VISIBLE_PER_DAY = 3;

// M14 §5: four `kind`s, each visually distinct — `projected` is
// deliberately greyed out (lower-opacity, muted tone) because completing an
// interval early or late moves it; it's a forecast, not a commitment, and
// must never look identical to a real `due`/`overdue` entry.
const KIND_CLASSES: Record<CalendarEntry['kind'], string> = {
  done: 'bg-success/10 text-success',
  overdue: 'bg-danger/10 text-danger',
  due: 'bg-warning/10 text-warning',
  projected: 'bg-surface-sunken text-text-muted opacity-60',
};

const KIND_LABELS: Record<CalendarEntry['kind'], string> = {
  done: 'Done',
  overdue: 'Overdue',
  due: 'Due',
  projected: 'Projected',
};

/** M14 §5's `/plants/calendar` month grid. */
export function PlantCalendarGrid({ month, entries }: PlantCalendarGridProps): ReactElement {
  const weeks = buildCalendarWeeks(month);
  const entriesByDay = new Map<string, CalendarEntry[]>();
  for (const entry of entries) {
    const existing = entriesByDay.get(entry.day);
    if (existing) {
      existing.push(entry);
    } else {
      entriesByDay.set(entry.day, [entry]);
    }
  }

  return (
    <div className="border-border overflow-hidden rounded-md border">
      <div className="border-border bg-surface-sunken grid grid-cols-7 border-b text-center text-xs font-medium">
        {WEEKDAY_LABELS.map((label) => (
          <div key={label} className="text-text-muted py-1.5">
            {label}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {weeks.flatMap((week) =>
          week.map(({ date, inMonth }) => {
            const dayEntries = entriesByDay.get(date) ?? [];
            const visible = dayEntries.slice(0, MAX_VISIBLE_PER_DAY);
            const extraCount = dayEntries.length - visible.length;
            return (
              <div
                key={date}
                className={`border-border bg-surface flex min-h-24 flex-col gap-1 border-b border-r p-1.5 last:border-r-0 ${
                  inMonth ? '' : 'bg-surface-sunken/40'
                }`}
              >
                <span className={`text-xs ${inMonth ? 'text-text' : 'text-text-muted'}`}>
                  {Number(date.slice(-2))}
                </span>
                {visible.map((entry, index) => (
                  <Link
                    key={`${entry.plant_id}-${entry.interval_id ?? 'none'}-${index}`}
                    to="/plants/$plantId"
                    params={{ plantId: entry.plant_id }}
                    title={`${entry.plant_name} · ${entry.action_name} · ${KIND_LABELS[entry.kind]}`}
                    className={`truncate rounded-sm px-1 py-0.5 text-[11px] leading-tight ${KIND_CLASSES[entry.kind]}`}
                  >
                    {entry.plant_name}
                  </Link>
                ))}
                {extraCount > 0 && (
                  <span className="text-text-muted text-[11px]">+{extraCount} more</span>
                )}
              </div>
            );
          }),
        )}
      </div>
    </div>
  );
}
