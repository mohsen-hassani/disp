import { createFileRoute } from '@tanstack/react-router';

import { SessionView } from '../components/learning/SessionView';

export const Route = createFileRoute('/_app/learning/$courseId/exercise/$sessionId')({
  component: ExerciseSessionRoute,
  staticData: { title: 'Exercise · DISP' },
});

function ExerciseSessionRoute() {
  const { courseId, sessionId } = Route.useParams();
  return <SessionView kind="exercise" courseId={courseId} sessionId={sessionId} />;
}
