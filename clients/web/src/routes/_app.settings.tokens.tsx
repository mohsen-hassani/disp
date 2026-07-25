import { createFileRoute } from '@tanstack/react-router';

import { TokensPage } from './-tokens';

export const Route = createFileRoute('/_app/settings/tokens')({
  component: TokensPage,
  staticData: { title: 'API tokens · DISP' },
});
