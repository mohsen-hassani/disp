import { createFileRoute, notFound } from '@tanstack/react-router';

import { isProblem } from '../api/problem';
import { noteDetailQueryOptions } from '../api/queries';
import { NoteDetailPage } from './-note-detail';
import { NotFoundPage } from './-not-found';

// §16.2: `404 notes.not_found` renders the not-found screen, not a toast —
// resolved in the loader (mirrors `_app.settings.$domain.tsx`'s `notFound()`
// pattern) so the component never even mounts against a note that doesn't
// exist or isn't visible to the caller.
export const Route = createFileRoute('/_app/notes/$noteId')({
  loader: async ({ params, context }) => {
    try {
      await context.queryClient.ensureQueryData(noteDetailQueryOptions(params.noteId));
    } catch (error) {
      if (isProblem(error) && error.status === 404) {
        throw notFound();
      }
      throw error;
    }
  },
  component: NoteDetailRoute,
  notFoundComponent: NotFoundPage,
  staticData: { title: 'Note · DISP' },
});

function NoteDetailRoute() {
  const { noteId } = Route.useParams();
  return <NoteDetailPage noteId={noteId} />;
}
