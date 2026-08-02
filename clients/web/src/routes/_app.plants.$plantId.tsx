import { createFileRoute, notFound } from '@tanstack/react-router';

import { isProblem } from '../api/problem';
import { plantDetailQueryOptions } from '../api/queries';
import { NotFoundPage } from './-not-found';
import { PlantDetailPage } from './-plant-detail';

// Same shape as `_app.notes.$noteId.tsx`: a 404 from the API becomes the
// not-found screen in the loader, so the component never mounts against a
// plant that doesn't exist or isn't visible to the caller.
export const Route = createFileRoute('/_app/plants/$plantId')({
  loader: async ({ params, context }) => {
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
