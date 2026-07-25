import { createFileRoute } from '@tanstack/react-router';

import { AccountPage } from './-account';

export const Route = createFileRoute('/_app/settings/account')({
  component: AccountPage,
  staticData: { title: 'Account · DISP' },
});
