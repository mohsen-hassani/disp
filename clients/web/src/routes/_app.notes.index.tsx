import { createFileRoute } from '@tanstack/react-router';

// Stub — M08 owns the real notes list (WEB-SPEC §16.1).
function NotesListPage() {
  return (
    <>
      <h1>Notes</h1>
      <p>Coming in M08.</p>
    </>
  );
}

export const Route = createFileRoute('/_app/notes/')({
  component: NotesListPage,
  staticData: { title: 'Notes · DISP' },
});
