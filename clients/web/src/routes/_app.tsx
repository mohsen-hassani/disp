import { createFileRoute, Outlet, redirect } from '@tanstack/react-router';

import { dashboardManifestQueryOptions } from '../api/queries';
import { getAuthState } from '../auth/authState';
import { isAuthenticated } from '../auth/guards';
import { AppShell } from '../components/layout/AppShell';
import { CreateNoteDialogProvider } from '../components/notes/CreateNoteDialogProvider';

// WEB-SPEC §9: every authenticated screen nests under this pathless layout,
// which owns the auth guard. By the time this ever runs, `AuthProvider`
// (main.tsx wraps the whole router in it) has already resolved bootstrap —
// it renders nothing but a skeleton itself while `loading`, so the router
// never even mounts mid-bootstrap. `revoked` is redirected here too: it's
// not "unauthenticated" in the anonymous sense, but it still can't stay on
// a guarded page — `hardLogout()` already navigates to `/login` itself when
// the transition happens live, this only covers reaching the URL directly
// (e.g. a second tab) while already revoked.
export const Route = createFileRoute('/_app')({
  beforeLoad: ({ location }) => {
    if (!isAuthenticated(getAuthState())) {
      throw redirect({ to: '/login', search: { next: location.href } });
    }
  },
  loader: async ({ context }) => {
    // Recommended resolution of the milestone's open question: the nav
    // needs the manifest to render correctly on first paint anyway, and
    // `/settings/:domain` (§9) must validate its param against it without a
    // network call — both need it already resolved by the time any child
    // route renders, not just eventually fetched.
    await context.queryClient.ensureQueryData(dashboardManifestQueryOptions());
  },
  component: AppLayout,
});

function AppLayout() {
  return (
    // §16.3/§16.5: the create-note dialog is reachable from any screen (the
    // `n` shortcut is global, not `/notes`-scoped) — mounted here, above
    // `AppShell`, so both it and every routed page underneath can reach the
    // one shared dialog instance via `useCreateNoteDialog()`.
    <CreateNoteDialogProvider>
      <AppShell>
        <Outlet />
      </AppShell>
    </CreateNoteDialogProvider>
  );
}
