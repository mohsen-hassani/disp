import { createFileRoute } from '@tanstack/react-router';

import { plantsCalendarQueryOptions } from '../api/queries';
import { currentMonth } from '../lib/calendar';
import { PlantCalendarPage } from './-plant-calendar';

interface CalendarSearch {
  month: string;
}

const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

// A static path, so it must never be matched by `_app.plants.$plantId` —
// TanStack Router ranks static segments above dynamic ones, so this resolves
// ahead of the `$plantId` route without any ordering directive.
export const Route = createFileRoute('/_app/plants/calendar')({
  component: PlantCalendarRoute,
  staticData: { title: 'Care calendar · DISP' },
  // The month is in the URL, so a particular month is linkable. Anything
  // malformed falls back to the current month rather than 404ing — the
  // server would reject it, and a bad query string is not worth an error page.
  validateSearch: (search: Record<string, unknown>): CalendarSearch => ({
    month:
      typeof search.month === 'string' && MONTH_PATTERN.test(search.month)
        ? search.month
        : currentMonth(),
  }),
  loaderDeps: ({ search }) => ({ month: search.month }),
  loader: ({ context, deps }) =>
    context.queryClient.ensureQueryData(plantsCalendarQueryOptions(deps.month)),
});

function PlantCalendarRoute() {
  const { month } = Route.useSearch();
  const navigate = Route.useNavigate();

  return (
    <PlantCalendarPage
      month={month}
      onMonthChange={(next) => void navigate({ search: () => ({ month: next }) })}
    />
  );
}
