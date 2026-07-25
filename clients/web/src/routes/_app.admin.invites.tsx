import { createFileRoute } from '@tanstack/react-router';

import { ForbiddenScreen, isAdmin } from '../auth/guards';
import { useAuth } from '../auth/useAuth';

// Stub — M07 owns the real invitations screen (WEB-SPEC §15.3). The
// admin-only check has to live here rather than in `beforeLoad` — see
// guards.tsx's `ForbiddenScreen` doc for why it renders in place instead of
// redirecting.
function InvitesPage() {
  const { state } = useAuth();
  if (!isAdmin(state)) {
    return <ForbiddenScreen />;
  }
  return (
    <>
      <h1>Invitations</h1>
      <p>Coming in M07.</p>
    </>
  );
}

export const Route = createFileRoute('/_app/admin/invites')({
  component: InvitesPage,
  staticData: { title: 'Invitations · DISP' },
});
