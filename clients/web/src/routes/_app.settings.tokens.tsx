import { createFileRoute } from '@tanstack/react-router';

// Stub — M07 owns the real API tokens screen (WEB-SPEC §15.2).
function TokensPage() {
  return (
    <>
      <h1>API tokens</h1>
      <p>Coming in M07.</p>
    </>
  );
}

export const Route = createFileRoute('/_app/settings/tokens')({
  component: TokensPage,
  staticData: { title: 'API tokens · DISP' },
});
