import { createFileRoute } from '@tanstack/react-router';

import { SessionView } from '../components/learning/SessionView';

export const Route = createFileRoute('/_app/learning/$courseId/quiz/$sessionId')({
  component: QuizSessionRoute,
  staticData: { title: 'Quiz · DISP' },
});

function QuizSessionRoute() {
  const { courseId, sessionId } = Route.useParams();
  return <SessionView kind="quiz" courseId={courseId} sessionId={sessionId} />;
}
