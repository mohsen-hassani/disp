import { createFileRoute } from '@tanstack/react-router';

// Stub — M07 owns the real account screen (WEB-SPEC §15.1).
function AccountPage() {
  return (
    <>
      <h1>Account</h1>
      <p>Coming in M07.</p>
    </>
  );
}

export const Route = createFileRoute('/_app/settings/account')({
  component: AccountPage,
  staticData: { title: 'Account · DISP' },
});
