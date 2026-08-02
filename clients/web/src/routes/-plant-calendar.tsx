import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { ArrowLeft, ChevronLeft, ChevronRight } from 'lucide-react';
import type { ReactElement } from 'react';

import { plantsCalendarQueryOptions } from '../api/queries';
import { CalendarLegend, CareCalendar } from '../components/plants/CareCalendar';
import { secondaryButtonClass } from '../components/plants/styles';
import { currentMonth, monthLabel, shiftMonth } from '../lib/calendar';

interface PlantCalendarPageProps {
  month: string;
  onMonthChange: (month: string) => void;
}

export function PlantCalendarPage({ month, onMonthChange }: PlantCalendarPageProps): ReactElement {
  const calendarQuery = useQuery(plantsCalendarQueryOptions(month));
  const isCurrentMonth = month === currentMonth();

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link
          to="/plants"
          className="text-text-muted hover:text-text mb-3 inline-flex items-center gap-1.5 text-sm"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          All plants
        </Link>
        <h1 className="text-text text-xl font-semibold">Care calendar</h1>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          aria-label="Previous month"
          className={secondaryButtonClass}
          onClick={() => onMonthChange(shiftMonth(month, -1))}
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </button>
        <h2
          aria-live="polite"
          className="text-text min-w-[10rem] text-center text-base font-medium"
        >
          {monthLabel(month)}
        </h2>
        <button
          type="button"
          aria-label="Next month"
          className={secondaryButtonClass}
          onClick={() => onMonthChange(shiftMonth(month, 1))}
        >
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
        {isCurrentMonth ? null : (
          <button
            type="button"
            className={secondaryButtonClass}
            onClick={() => onMonthChange(currentMonth())}
          >
            Today
          </button>
        )}
      </div>

      {calendarQuery.isPending ? (
        <div aria-busy="true" className="border-border h-96 animate-pulse rounded-md border" />
      ) : calendarQuery.isError ? (
        <div className="border-border rounded-md border p-4">
          <p className="text-text mb-3 text-sm">Could not load the calendar.</p>
          <button
            type="button"
            className={secondaryButtonClass}
            onClick={() => void calendarQuery.refetch()}
          >
            Retry
          </button>
        </div>
      ) : (
        <>
          <CareCalendar month={month} entries={calendarQuery.data.entries} />
          <CalendarLegend />
          <p className="text-text-muted text-xs">
            Past days show what was actually done. Today onwards is derived from each plant’s
            schedule — completing something early or late moves every later occurrence, so projected
            days are an estimate.
          </p>
        </>
      )}
    </div>
  );
}
