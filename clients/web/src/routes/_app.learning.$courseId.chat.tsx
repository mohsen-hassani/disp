import { createFileRoute } from '@tanstack/react-router';

import { ChatPage } from '../components/learning/ChatPage';

export const Route = createFileRoute('/_app/learning/$courseId/chat')({
  component: ChatRoute,
  staticData: { title: 'Chat · DISP' },
});

function ChatRoute() {
  const { courseId } = Route.useParams();
  return <ChatPage courseId={courseId} />;
}
