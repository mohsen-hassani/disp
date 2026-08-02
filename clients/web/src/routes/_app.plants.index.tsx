import { createFileRoute } from '@tanstack/react-router';

import { PlantsListPage } from './-plants';

interface PlantsSearch {
  q?: string;
}

// Mirrors `_app.notes.index.tsx`: the search term lives in the URL so a
// filtered list is linkable and survives a reload.
export const Route = createFileRoute('/_app/plants/')({
  component: PlantsRouteComponent,
  staticData: { title: 'Plants · DISP' },
  validateSearch: (search: Record<string, unknown>): PlantsSearch => ({
    q: typeof search.q === 'string' && search.q ? search.q : undefined,
  }),
});

function PlantsRouteComponent() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();

  return (
    <PlantsListPage
      q={search.q}
      onQChange={(q) => void navigate({ search: () => ({ q }), replace: true })}
    />
  );
}
