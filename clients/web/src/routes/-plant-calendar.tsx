import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { ReactElement } from 'react';

import { plantCalendarQueryOptions } from '../api/queries';
import { currentMonth, monthLabel, shiftMonth } from '../components/plants/calendarMonth';
import { PlantCalendarGrid } from '../components/plants/PlantCalendarGrid';

interface PlantCalendarPageProps {
  month: string;
  onMonthChange: (month: string) => void;
}

const iconButtonClass =
  'text-text-muted focus-visible:outline-accent flex h-9 w-9 items-center justify-center rounded-sm focus-visible:outline focus-visible:outline-2';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

// Router-ignored (leading `-`) — see `-login.tsx`'s doc for why.
export function PlantCalendarPage({ month, onMonthChange }: PlantCalendarPageProps): ReactElement {
  const calendarQuery = useQuery(plantCalendarQueryOptions(month));

  return (
    <>
      <h1>Plant calendar</h1>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-label="Previous month"
            onClick={() => onMonthChange(shiftMonth(month, -1))}
            className={iconButtonClass}
          >
            <ChevronLeft className="h-5 w-5" aria-hidden="true" />
          </button>
          <span className="text-text w-36 text-center text-sm font-medium">
            {monthLabel(month)}
          </span>
          <button
            type="button"
            aria-label="Next month"
            onClick={() => onMonthChange(shiftMonth(month, 1))}
            className={iconButtonClass}
          >
            <ChevronRight className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        <button
          type="button"
          onClick={() => onMonthChange(currentMonth())}
          className={secondaryButtonClass}
        >
          Today
        </button>
      </div>

      {calendarQuery.isPending && (
        <p aria-busy="true" className="text-text-muted text-sm">
          Loading…
        </p>
      )}
      {calendarQuery.isError && (
        <p role="alert" className="text-text-muted text-sm">
          Failed to load the calendar.
        </p>
      )}
      {calendarQuery.isSuccess && (
        <PlantCalendarGrid month={month} entries={calendarQuery.data.entries} />
      )}
    </>
  );
}
