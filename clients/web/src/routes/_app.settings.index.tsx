import { createFileRoute } from '@tanstack/react-router';

// Stub — M06 owns the real settings index (WEB-SPEC §14).
function SettingsIndexPage() {
  return (
    <>
      <h1>Settings</h1>
      <p>Coming in M06.</p>
    </>
  );
}

export const Route = createFileRoute('/_app/settings/')({
  component: SettingsIndexPage,
  staticData: { title: 'Settings · DISP' },
});
