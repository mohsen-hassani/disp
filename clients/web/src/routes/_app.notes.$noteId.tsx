import { createFileRoute } from '@tanstack/react-router';

// Stub — M08 owns the real note detail screen (WEB-SPEC §16.2). The route
// table's document title is dynamic ("<note title> · DISP"), which needs
// the note itself loaded first; until M08 fetches it, this static
// placeholder stands in — that milestone can set `document.title` itself
// once real data exists rather than this route guessing at a shape.
function NoteDetailPage() {
  return (
    <>
      <h1>Note</h1>
      <p>Coming in M08.</p>
    </>
  );
}

export const Route = createFileRoute('/_app/notes/$noteId')({
  component: NoteDetailPage,
  staticData: { title: 'Note · DISP' },
});
