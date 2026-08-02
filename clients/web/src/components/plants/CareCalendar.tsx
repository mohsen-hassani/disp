import type { ReactElement } from 'react';

import type { CalendarEntry } from '../../api/generated';
import { type GridDay, buildMonthGrid, groupByDay, weekdayLabels } from '../../lib/calendar';

interface CareCalendarProps {
  month: string;
  entries: CalendarEntry[];
}

const MAX_PER_CELL = 3;

/**
 * How each kind reads. `projected` is deliberately the quietest: it is a
 * forecast derived from the current cadence, and completing anything early
 * or late moves every later occurrence, so it must not look like a
 * commitment the way `due` and `overdue` do.
 */
const KIND_CLASS: Record<CalendarEntry['kind'], string> = {
  done: 'bg-surface-sunken text-text-muted line-through',
  overdue: 'bg-danger text-accent-text',
  due: 'bg-accent text-accent-text',
  projected: 'border-border text-text-muted border border-dashed',
};

const KIND_LABEL: Record<CalendarEntry['kind'], string> = {
  done: 'done',
  overdue: 'overdue',
  due: 'due',
  projected: 'projected',
};

export function CareCalendar({ month, entries }: CareCalendarProps): ReactElement {
  const grid = buildMonthGrid(month);
  const byDay = groupByDay(entries);

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[42rem]">
        <div className="text-text-muted grid grid-cols-7 gap-1 pb-1 text-xs">
          {weekdayLabels().map((label) => (
            <div key={label} className="px-1 font-medium">
              {label}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-7 gap-1">
          {grid.map((cell) => (
            <DayCell key={cell.day} cell={cell} entries={byDay.get(cell.day) ?? []} />
          ))}
        </div>
      </div>
    </div>
  );
}

function DayCell({ cell, entries }: { cell: GridDay; entries: CalendarEntry[] }): ReactElement {
  const visible = entries.slice(0, MAX_PER_CELL);
  const hidden = entries.length - visible.length;

  return (
    <div
      className={[
        'border-border min-h-[5.5rem] rounded-sm border p-1',
        cell.inMonth ? 'bg-surface' : 'bg-surface-sunken opacity-60',
        cell.isToday ? 'outline-accent outline outline-2 -outline-offset-1' : '',
      ].join(' ')}
    >
      <div className="mb-1 flex items-baseline justify-between px-0.5">
        <span
          className={`text-xs ${cell.isToday ? 'text-accent font-semibold' : 'text-text-muted'}`}
        >
          {cell.dayOfMonth}
        </span>
        {cell.isToday ? <span className="text-accent text-[10px]">today</span> : null}
      </div>

      <ul className="flex flex-col gap-0.5">
        {visible.map((entry) => (
          <li
            key={`${entry.kind}-${entry.interval_id ?? entry.log_id}-${entry.day}`}
            className={`truncate rounded-sm px-1 py-0.5 text-[11px] ${KIND_CLASS[entry.kind]}`}
            title={`${entry.action_name} — ${entry.plant_name} (${KIND_LABEL[entry.kind]})`}
          >
            <span className="sr-only">{KIND_LABEL[entry.kind]}: </span>
            {entry.action_name} · {entry.plant_name}
          </li>
        ))}
        {hidden > 0 ? <li className="text-text-muted px-1 text-[11px]">+{hidden} more</li> : null}
      </ul>
    </div>
  );
}

/** Shown under the grid so the colour coding is not the only cue. */
export function CalendarLegend(): ReactElement {
  return (
    <ul className="text-text-muted flex flex-wrap gap-4 text-xs">
      {(Object.keys(KIND_LABEL) as CalendarEntry['kind'][]).map((kind) => (
        <li key={kind} className="flex items-center gap-1.5">
          <span
            className={`inline-block h-3 w-3 rounded-sm ${KIND_CLASS[kind]}`}
            aria-hidden="true"
          />
          {KIND_LABEL[kind]}
        </li>
      ))}
    </ul>
  );
}
