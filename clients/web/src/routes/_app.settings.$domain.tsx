import { createFileRoute, notFound } from '@tanstack/react-router';

import {
  dashboardManifestQueryOptions,
  settingsPanelDomains,
  settingsQueryOptions,
} from '../api/queries';
import { NotFoundPage } from './-not-found';
import { ModuleSettingsPage } from './-settings-domain';

// The domain-validity check in `beforeLoad` is M04's; this milestone adds
// the loader that actually fetches the values, so the form never renders
// against an empty `initialValue` it would then immediately overwrite.
export const Route = createFileRoute('/_app/settings/$domain')({
  beforeLoad: async ({ params, context }) => {
    // §9: must not read the manifest with a bare `getQueryData` — on a
    // direct/fresh navigation to this URL (not a client-side `<Link>` click
    // from an already-loaded page), `_app`'s own loader (which populates
    // this same cache entry) hasn't necessarily resolved yet by the time a
    // child route's `beforeLoad` runs, since TanStack Router runs every
    // matched route's `beforeLoad` before any route's `loader`. Caught live
    // in M11's e2e suite: a fresh `/settings/core` load 404'd even though
    // `core` is a real manifest domain. `ensureQueryData` both waits for an
    // in-flight fetch and de-dupes against `_app`'s identical query.
    const manifest = await context.queryClient.ensureQueryData(dashboardManifestQueryOptions());
    const validDomains = settingsPanelDomains(manifest);
    if (!validDomains.includes(params.domain)) {
      throw notFound();
    }
  },
  loader: ({ params, context }) =>
    context.queryClient.ensureQueryData(settingsQueryOptions(params.domain)),
  component: RouteComponent,
  notFoundComponent: NotFoundPage,
});

function RouteComponent() {
  const { domain } = Route.useParams();
  return <ModuleSettingsPage domain={domain} />;
}
