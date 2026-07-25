import { createFileRoute, notFound } from '@tanstack/react-router';

import { dashboardManifestQueryOptions, settingsPanelDomains } from '../api/queries';
import { NotFoundPage } from './-not-found';

// Stub — M06 owns the real generic settings-panel renderer (WEB-SPEC §14).
// The domain-validity check below is this milestone's job either way:
// `_app.tsx`'s loader has already resolved `['dashboard','manifest']` into
// the query cache by the time this route can be reached, so reading it back
// with `getQueryData` (never `ensureQueryData`/`fetchQuery`) is what makes
// this a synchronous, no-network-call check, per §9.
function ModuleSettingsPage() {
  const { domain } = Route.useParams();
  return (
    <>
      <h1>{domain}</h1>
      <p>Coming in M06.</p>
    </>
  );
}

export const Route = createFileRoute('/_app/settings/$domain')({
  beforeLoad: ({ params, context }) => {
    const manifest = context.queryClient.getQueryData(dashboardManifestQueryOptions().queryKey);
    const validDomains = manifest ? settingsPanelDomains(manifest) : [];
    if (!validDomains.includes(params.domain)) {
      throw notFound();
    }
  },
  component: ModuleSettingsPage,
  notFoundComponent: NotFoundPage,
  staticData: { title: 'Settings · DISP' },
});
