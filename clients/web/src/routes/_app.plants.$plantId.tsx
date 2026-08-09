import { createFileRoute, notFound } from '@tanstack/react-router';

import { isProblem } from '../api/problem';
import { plantDetailQueryOptions } from '../api/queries';
import { NotFoundPage } from './-not-found';
import { PlantDetailPage } from './-plant-detail';

// M14 §2: `/plants/new` and `/plants/calendar` are separate static route
// files, and TanStack Router ranks static segments above a dynamic one
// automatically — so this route only ever matches when nothing static did.
// A garbage id (neither a static segment nor a real plant) would otherwise
// reach `plantsGet` and come back as a confusing 422 rather than a clean
// 404 — validating the shape here lets a non-match fall straight through to
// the same not-found path as a real 404, without a network round trip.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const Route = createFileRoute('/_app/plants/$plantId')({
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
  component: PlantDetailRoute,
  notFoundComponent: NotFoundPage,
  staticData: { title: 'Plant · DISP' },
});

function PlantDetailRoute() {
  const { plantId } = Route.useParams();
  return <PlantDetailPage plantId={plantId} />;
}
