import { createFileRoute } from '@tanstack/react-router';

import { NotesPage } from '../components/learning/NotesPage';

export const Route = createFileRoute('/_app/learning/$courseId/notes')({
  component: NotesRoute,
  staticData: { title: 'Notes · DISP' },
});

function NotesRoute() {
  const { courseId } = Route.useParams();
  return <NotesPage courseId={courseId} />;
}
