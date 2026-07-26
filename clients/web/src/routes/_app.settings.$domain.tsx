import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createFileRoute, notFound } from '@tanstack/react-router';
import { type ReactElement, useState } from 'react';

import { settingsUpdate } from '../api/generated';
import { parseProblem } from '../api/problem';
import {
  dashboardManifestQueryOptions,
  describeSettingsError,
  filterDirtyValues,
  settingsPanelDomains,
  settingsQueryOptions,
} from '../api/queries';
import { qk } from '../api/queryKeys';
import { SavedDataLabel } from '../components/feedback/SavedDataLabel';
import { useToast } from '../components/feedback/ToastProvider';
import { SchemaForm, type ServerFieldError } from '../components/schema-form/SchemaForm';
import type { JsonSchemaDoc } from '../components/schema-form/types';
import { useOfflineState } from '../hooks/useOfflineState';
import { NotFoundPage } from './-not-found';

// The domain-validity check in `beforeLoad` is M04's; this milestone adds
// the loader that actually fetches the values, so the form never renders
// against an empty `initialValue` it would then immediately overwrite.
export const Route = createFileRoute('/_app/settings/$domain')({
  beforeLoad: ({ params, context }) => {
    const manifest = context.queryClient.getQueryData(dashboardManifestQueryOptions().queryKey);
    const validDomains = manifest ? settingsPanelDomains(manifest) : [];
    if (!validDomains.includes(params.domain)) {
      throw notFound();
    }
  },
  loader: ({ params, context }) =>
    context.queryClient.ensureQueryData(settingsQueryOptions(params.domain)),
  component: ModuleSettingsPage,
  notFoundComponent: NotFoundPage,
});

function ModuleSettingsPage(): ReactElement {
  const { domain } = Route.useParams();
  const manifestQuery = useQuery(dashboardManifestQueryOptions());
  const valuesQuery = useQuery(settingsQueryOptions(domain));
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const isOffline = useOfflineState();
  const [formError, setFormError] = useState<string | undefined>();
  const [serverErrors, setServerErrors] = useState<ServerFieldError[] | undefined>();

  const module = manifestQuery.data?.modules.find((candidate) => candidate.domain === domain);
  // §14.1's data model allows a module several panels, but the backend's
  // own domain→panel lookup (`registry.settings_panel_for_domain`) only
  // ever resolves the first one registered under a given domain prefix —
  // GET/PUT /api/settings/{domain} can only ever serve that one panel, so
  // there's nothing to gain from rendering the rest.
  const panel = module?.settings_panels[0];

  if (!panel) {
    return <p role="alert">This settings panel could not be found.</p>;
  }
  if (valuesQuery.isPending) {
    return <p aria-busy="true">Loading…</p>;
  }
  if (valuesQuery.isError) {
    return <p role="alert">Failed to load settings.</p>;
  }

  const handleSubmit = async (
    values: Record<string, unknown>,
    dirtyFields: Record<string, unknown>,
  ): Promise<void> => {
    setFormError(undefined);
    setServerErrors(undefined);

    const payload = filterDirtyValues(values, dirtyFields);
    const { data, error, response } = await settingsUpdate({ path: { domain }, body: payload });
    if (!response?.ok || !data) {
      const problem = parseProblem(response ?? new Response(null, { status: 0 }), error);
      if (problem.status === 422 && problem.errors) {
        setServerErrors(problem.errors);
      } else {
        setFormError(describeSettingsError(problem));
      }
      return;
    }

    // §14.5: success resets dirty state to the server's response — writing
    // the PUT's own response (already masked/normalized identically to
    // GET) directly into the cache is what `SchemaForm` watches to do that,
    // without a second round-trip to re-fetch what this response already is.
    queryClient.setQueryData(qk.settings.domain(domain), data);
    showToast('Settings saved.', 'success');
  };

  return (
    <>
      <h1>{panel.title}</h1>
      {panel.description && <p className="text-text-muted text-sm">{panel.description}</p>}
      <SavedDataLabel show={isOffline} />
      <SchemaForm
        schema={panel.schema as JsonSchemaDoc}
        initialValue={valuesQuery.data}
        onSubmit={handleSubmit}
        error={formError}
        serverErrors={serverErrors}
      />
    </>
  );
}
