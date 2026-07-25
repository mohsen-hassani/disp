import { createFileRoute } from '@tanstack/react-router';

// Stub — M05 owns the real tile-grid dashboard (WEB-SPEC §13).
function DashboardPage() {
  return (
    <>
      <h1>Dashboard</h1>
      <p>Coming in M05.</p>
    </>
  );
}

export const Route = createFileRoute('/_app/')({
  component: DashboardPage,
  staticData: { title: 'Dashboard · DISP' },
});
