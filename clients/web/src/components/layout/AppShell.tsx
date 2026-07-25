import { useQuery } from '@tanstack/react-query';
import type { ReactElement, ReactNode } from 'react';

import { dashboardManifestQueryOptions } from '../../api/queries';
import { isAdmin } from '../../auth/guards';
import { useAuth } from '../../auth/useAuth';
import { BottomNav } from './BottomNav';
import { computeNavItems } from './navItems';
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
  const manifestDomains = manifestQuery.data?.modules.map((module) => module.domain) ?? [];
  const items = computeNavItems({ manifestDomains, isAdmin: isAdmin(state) });

  return (
    <div className="flex min-h-screen flex-col px-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)]">
      <TopBar />
      <div className="flex flex-1">
        <SideNav items={items} />
        <main id="main-content" className="min-w-0 flex-1 p-4 pb-20 md:p-6 md:pb-6">
          {children}
        </main>
      </div>
      <BottomNav items={items} />
    </div>
  );
}
