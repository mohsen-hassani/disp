import { createFileRoute } from '@tanstack/react-router';

import { AcceptInvitePage } from './-accept-invite';

export const Route = createFileRoute('/accept-invite')({
  component: AcceptInvitePage,
  staticData: { title: 'Accept invitation · DISP' },
});
