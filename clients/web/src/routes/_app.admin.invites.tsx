import { createFileRoute } from '@tanstack/react-router';

import { ForbiddenScreen, isAdmin } from '../auth/guards';
import { useAuth } from '../auth/useAuth';
import { InvitesPage } from './-invites';

// The admin-only check has to live here rather than in `beforeLoad` — see
// guards.tsx's `ForbiddenScreen` doc for why it renders in place instead of
// redirecting.
function Guarded() {
  const { state } = useAuth();
  if (!isAdmin(state)) {
    return <ForbiddenScreen />;
  }
  return <InvitesPage />;
}

export const Route = createFileRoute('/_app/admin/invites')({
  component: Guarded,
  staticData: { title: 'Invitations · DISP' },
});
