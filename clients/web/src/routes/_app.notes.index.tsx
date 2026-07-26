import { createFileRoute } from '@tanstack/react-router';
import { useEffect } from 'react';

import { useCreateNoteDialog } from '../components/notes/CreateNoteDialogProvider';
import { NotesListPage } from './-notes';

interface NotesSearch {
  q?: string;
  pinned?: boolean;
  /** §17.1's PWA app shortcut ("New note") links to `/notes?new=1`. */
  new?: boolean;
}

// §16.1: the search term (and the pinned-only filter) live in the URL so a
// search is linkable and survives reload.
export const Route = createFileRoute('/_app/notes/')({
  component: NotesRouteComponent,
  staticData: { title: 'Notes · DISP' },
  validateSearch: (search: Record<string, unknown>): NotesSearch => ({
    q: typeof search.q === 'string' && search.q ? search.q : undefined,
    pinned: search.pinned === true ? true : undefined,
    new: search.new === '1' || search.new === true ? true : undefined,
  }),
});

function NotesRouteComponent() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const { open } = useCreateNoteDialog();

  useEffect(() => {
    if (search.new) {
      open();
      // Consumed once — otherwise reloading or navigating back would reopen it.
      void navigate({ search: (prev) => ({ ...prev, new: undefined }), replace: true });
    }
  }, [search.new]);

  return (
    <NotesListPage
      q={search.q}
      pinned={search.pinned}
      onQChange={(q) => void navigate({ search: (prev) => ({ ...prev, q }), replace: true })}
      onPinnedChange={(pinned) =>
        void navigate({ search: (prev) => ({ ...prev, pinned }), replace: true })
      }
    />
  );
}
