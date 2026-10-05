import { createFileRoute } from '@tanstack/react-router';

import { learningPathQueryOptions } from '../api/queries';
import { PathPage } from '../components/learning/PathPage';

export const Route = createFileRoute('/_app/learning/$courseId/path')({
  loader: async ({ params, context }) => {
    await context.queryClient.ensureQueryData(learningPathQueryOptions(params.courseId));
  },
  component: PathRoute,
  staticData: { title: 'Learning path · DISP' },
});

function PathRoute() {
  const { courseId } = Route.useParams();
  return <PathPage courseId={courseId} />;
}
