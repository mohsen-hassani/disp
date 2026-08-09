import { createFileRoute } from '@tanstack/react-router';

import { currentMonth, isValidMonth } from '../components/plants/calendarMonth';
import { PlantCalendarPage } from './-plant-calendar';

interface PlantCalendarSearch {
  month?: string;
}

// M14 §5: "Month navigation writes `?month=YYYY-MM` to the URL (validated
// in `validateSearch`) so a month is linkable and back/forward works" —
// `month` stays optional in the validated shape (an invalid value collapses
// to `undefined`, not a thrown error) so a bare `/plants/calendar` link
// needs no `search` prop; the component below is what actually falls back
// to the current month, the same "degrade, don't break" rule the rest of
// the client uses for a manifest-declared icon/size it doesn't recognise.
export const Route = createFileRoute('/_app/plants/calendar')({
  component: PlantCalendarRouteComponent,
  staticData: { title: 'Plant calendar · DISP' },
  validateSearch: (search: Record<string, unknown>): PlantCalendarSearch => ({
    month:
      typeof search.month === 'string' && isValidMonth(search.month) ? search.month : undefined,
  }),
});

function PlantCalendarRouteComponent() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const month = search.month ?? currentMonth();

  return (
    <PlantCalendarPage
      month={month}
      // Deliberately not `replace: true` — each month change is a discrete
      // action (unlike debounced search typing), and back/forward through
      // visited months is part of the requirement.
      onMonthChange={(nextMonth) => void navigate({ search: { month: nextMonth } })}
    />
  );
}
