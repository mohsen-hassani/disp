import { createFileRoute, notFound } from '@tanstack/react-router';

import { isProblem } from '../api/problem';
import { plantDetailQueryOptions } from '../api/queries';
import { NotFoundPage } from './-not-found';
import { PlantEditPage } from './-plant-edit';

// A file-based sibling of `_app.plants.$plantId.tsx`, not nested under it
// (that route has no `Outlet`) — so it needs its own loader, same
// UUID-validate-then-`ensureQueryData` pattern, rather than inheriting the
// parent's.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const Route = createFileRoute('/_app/plants/$plantId/edit')({
  loader: async ({ params, context }) => {
    if (!UUID_RE.test(params.plantId)) {
      throw notFound();
    }
    try {
      await context.queryClient.ensureQueryData(plantDetailQueryOptions(params.plantId));
    } catch (error) {
      if (isProblem(error) && error.status === 404) {
        throw notFound();
      }
      throw error;
    }
  },
  component: PlantEditRoute,
  notFoundComponent: NotFoundPage,
  staticData: { title: 'Edit plant · DISP' },
});

function PlantEditRoute() {
  const { plantId } = Route.useParams();
  return <PlantEditPage plantId={plantId} />;
}
