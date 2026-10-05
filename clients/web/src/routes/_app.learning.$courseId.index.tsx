import { createFileRoute, notFound } from '@tanstack/react-router';

import { isProblem } from '../api/problem';
import { learningCourseQueryOptions } from '../api/queries';
import { CourseDetailPage } from '../components/learning/CourseDetail';
import { NotFoundPage } from './-not-found';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const Route = createFileRoute('/_app/learning/$courseId/')({
  loader: async ({ params, context }) => {
    if (!UUID_RE.test(params.courseId)) {
      throw notFound();
    }
    try {
      await context.queryClient.ensureQueryData(learningCourseQueryOptions(params.courseId));
    } catch (error) {
      if (isProblem(error) && error.status === 404) {
        throw notFound();
      }
      throw error;
    }
  },
  component: CourseDetailRoute,
  notFoundComponent: NotFoundPage,
  staticData: { title: 'Course · DISP' },
});

function CourseDetailRoute() {
  const { courseId } = Route.useParams();
  return <CourseDetailPage courseId={courseId} />;
}
