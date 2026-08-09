import { createFileRoute } from '@tanstack/react-router';

import { PlantsListPage } from './-plants';

interface PlantsSearch {
  q?: string;
}

// M14 §5: `q` lives in the URL so a search is linkable and survives reload — same convention as `_app.notes.index.tsx`.
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
      onQChange={(q) => void navigate({ search: (prev) => ({ ...prev, q }), replace: true })}
    />
  );
}
