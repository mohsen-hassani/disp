import type { ReactElement } from 'react';

import { useCreateNoteDialog } from '../components/notes/CreateNoteDialogProvider';
import { NoteList } from '../components/notes/NoteList';

interface NotesListPageProps {
  q: string | undefined;
  pinned: boolean | undefined;
  onQChange: (q: string | undefined) => void;
  onPinnedChange: (pinned: boolean | undefined) => void;
}

// Router-ignored (leading `-`) — see -login.tsx's doc for why. `q`/`pinned`
// and their setters come in as plain props rather than this file reading
// `useSearch`/`useNavigate` itself — the real route
// (`_app.notes.index.tsx`) owns that binding against its own typed `Route`
// object (a generic `strict: false` read fought the router's search-schema
// typing without adding anything, since this file is only ever mounted
// under that one route in the real app anyway) — which also keeps this
// component testable with plain props and no router search machinery.
export function NotesListPage({
  q,
  pinned,
  onQChange,
  onPinnedChange,
}: NotesListPageProps): ReactElement {
  const { open } = useCreateNoteDialog();

  return (
    <>
      <h1>Notes</h1>
      <NoteList
        q={q}
        pinned={pinned}
        onQChange={onQChange}
        onPinnedChange={onPinnedChange}
        onNewNote={open}
      />
    </>
  );
}
