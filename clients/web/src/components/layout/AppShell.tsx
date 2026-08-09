import { useQuery } from '@tanstack/react-query';
import { type ReactElement, type ReactNode, useState } from 'react';

import { dashboardManifestQueryOptions } from '../../api/queries';
import { isAdmin } from '../../auth/guards';
import { useAuth } from '../../auth/useAuth';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { useCreateNoteDialog } from '../notes/CreateNoteDialogProvider';
import { ShortcutsDialog } from '../shortcuts/ShortcutsDialog';
import { OfflineBanner } from '../feedback/OfflineBanner';
import { BottomNav } from './BottomNav';
import { computeNavSections } from './navItems';
import { SideNav } from './SideNav';
import { TopBar } from './TopBar';

interface AppShellProps {
  children: ReactNode;
}

// WEB-SPEC §12.1's structure. `routes/_app.tsx`'s loader already resolved
// `['dashboard','manifest']` before this ever mounts (§9's "no network call"
// requirement for `/settings/:domain`), so this `useQuery` call only ever
// reads that cache — it's the shared nav-items source SideNav and BottomNav
// both consume, per the milestone's own resolved open question (compute the
// manifest-derived list once, not twice, so the two navs can't drift apart).
export function AppShell({ children }: AppShellProps): ReactElement {
  const { state } = useAuth();
  const manifestQuery = useQuery(dashboardManifestQueryOptions());
  const sections = computeNavSections({
    modules: manifestQuery.data?.modules ?? [],
    isAdmin: isAdmin(state),
  });

  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const { open: openCreateNote } = useCreateNoteDialog();
  useKeyboardShortcuts({
    onOpenCreateNote: openCreateNote,
    onOpenShortcuts: () => setShortcutsOpen(true),
  });

  return (
    <div className="flex min-h-screen flex-col px-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)]">
      <OfflineBanner />
      <TopBar />
      <div className="flex flex-1">
        <SideNav sections={sections} />
        <main
          id="main-content"
          className="min-w-0 flex-1 p-4 pb-20 md:p-6 md:pb-6 xl:mx-auto xl:max-w-content"
        >
          {children}
        </main>
      </div>
      <BottomNav sections={sections} />
      <ShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </div>
  );
}
