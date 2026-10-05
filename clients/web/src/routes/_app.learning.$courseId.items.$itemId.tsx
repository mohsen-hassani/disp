import { createFileRoute } from '@tanstack/react-router';

import { learningPathItemContentQueryOptions } from '../api/queries';
import { PathItemPage } from '../components/learning/PathItemPage';

export const Route = createFileRoute('/_app/learning/$courseId/items/$itemId')({
  loader: async ({ params, context }) => {
    await context.queryClient.ensureQueryData(learningPathItemContentQueryOptions(params.itemId));
  },
  component: PathItemRoute,
  staticData: { title: 'Lesson · DISP' },
});

function PathItemRoute() {
  const { courseId, itemId } = Route.useParams();
  return <PathItemPage courseId={courseId} itemId={itemId} />;
}
