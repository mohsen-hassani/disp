import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterAll, afterEach, beforeAll, expect, it } from 'vitest';

import { client } from '../../../src/api/client';
import type { DashboardManifestResponse, SettingsUpdateResponse } from '../../../src/api/generated';
import { qk } from '../../../src/api/queryKeys';
import { ToastProvider } from '../../../src/components/feedback/ToastProvider';
import type { JsonSchemaDoc } from '../../../src/components/schema-form/types';
import { ModuleSettingsPage } from '../../../src/routes/-settings-domain';
import { server } from '../../mocks/server';

// This route's own test file is the demonstration case for §23.2's MSW
// layer (tests/mocks/handlers.ts + server.ts): both GETs a real settings
// screen fires (manifest, then panel values) go through the shared,
// generated-type-checked handlers, with only the PUT overridden per test —
// closer to how the real API actually behaves than a hand-rolled fetch spy
// for every call.
beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  server.resetHandlers();
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
  server.close();
});

const schema: JsonSchemaDoc = {
  type: 'object',
  properties: {
    label: { type: 'string', title: 'Label' },
    enabled: { type: 'boolean', title: 'Enabled' },
  },
};

function manifest(domain: string): DashboardManifestResponse {
  return {
    platform_version: '0.1.0',
    modules: [
      {
        domain,
        name: 'Demo',
        version: '1.0.0',
        description: null,
        tiles: [],
        notification_types: [],
        settings_panels: [
          {
            key: `${domain}.settings`,
            title: 'Demo settings',
            description: null,
            scope: 'global',
            schema: schema as Record<string, unknown>,
          },
        ],
      },
    ],
  };
}

function mockGetEndpoints(domain: string, values: Record<string, unknown>): void {
  server.use(
    http.get('/api/dashboard/manifest', () =>
      HttpResponse.json<DashboardManifestResponse>(manifest(domain)),
    ),
    http.get('/api/settings/:domain', () => HttpResponse.json(values)),
  );
}

async function renderSettings(domain: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const rootRoute = createRootRoute({
    component: () => (
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <ModuleSettingsPage domain={domain} />
        </ToastProvider>
      </QueryClientProvider>
    ),
  });
  const router = createRouter({
    routeTree: rootRoute,
    history: createMemoryHistory({ initialEntries: ['/'] }),
  });
  await router.load();
  return { ...render(<RouterProvider router={router} />), queryClient };
}

it('renders the panel title/description and the generated form from the manifest schema', async () => {
  mockGetEndpoints('demo', { label: 'hello', enabled: true });
  await renderSettings('demo');

  expect(await screen.findByRole('heading', { name: 'Demo settings' })).toBeInTheDocument();
  expect(screen.getByLabelText('Label')).toHaveValue('hello');
});

it('renders the not-found copy for a domain absent from the manifest', async () => {
  mockGetEndpoints('demo', {});
  await renderSettings('unknown-domain');
  expect(await screen.findByRole('alert')).toHaveTextContent(/could not be found/i);
});

// Test 33: only the keys the user actually changed reach the PUT payload —
// an untouched field (including a masked "***" secret) must never be
// echoed back.
it('sends only the dirty keys in the settings PUT payload (case 33)', async () => {
  mockGetEndpoints('demo', { label: 'hello', enabled: true });
  let putBody: unknown;
  server.use(
    http.put('/api/settings/:domain', async ({ request }) => {
      putBody = await request.json();
      return HttpResponse.json<SettingsUpdateResponse>({ label: 'changed', enabled: true });
    }),
  );
  const user = userEvent.setup();
  await renderSettings('demo');

  await user.clear(await screen.findByLabelText('Label'));
  await user.type(screen.getByLabelText('Label'), 'changed');
  await user.click(screen.getByRole('button', { name: /^save$/i }));

  await waitFor(() => expect(putBody).toEqual({ label: 'changed' }));
});

it('a 422 error maps to its field via the shared §19.3 mapper', async () => {
  mockGetEndpoints('demo', { label: 'hello', enabled: true });
  server.use(
    http.put(
      '/api/settings/:domain',
      () =>
        new HttpResponse(
          JSON.stringify({
            type: 'about:blank',
            title: 'Validation error',
            status: 422,
            detail: 'Invalid input.',
            instance: '/api/settings/demo',
            code: 'validation_error',
            request_id: 'req-settings',
            errors: [{ loc: ['body', 'label'], msg: 'Too long.' }],
          }),
          { status: 422, headers: { 'Content-Type': 'application/json' } },
        ),
    ),
  );
  const user = userEvent.setup();
  await renderSettings('demo');

  await user.clear(await screen.findByLabelText('Label'));
  await user.type(screen.getByLabelText('Label'), 'x'.repeat(10));
  await user.click(screen.getByRole('button', { name: /^save$/i }));

  await waitFor(() => expect(screen.getByText('Too long.')).toBeInTheDocument());
});

it('a successful save writes the response into the cache and shows a toast', async () => {
  mockGetEndpoints('demo', { label: 'hello', enabled: true });
  server.use(
    http.put('/api/settings/:domain', () =>
      HttpResponse.json<SettingsUpdateResponse>({ label: 'changed', enabled: true }),
    ),
  );
  const user = userEvent.setup();
  const { queryClient } = await renderSettings('demo');

  await user.clear(await screen.findByLabelText('Label'));
  await user.type(screen.getByLabelText('Label'), 'changed');
  await user.click(screen.getByRole('button', { name: /^save$/i }));

  await waitFor(() => expect(screen.getByText('Settings saved.')).toBeInTheDocument());
  expect(queryClient.getQueryData(qk.settings.domain('demo'))).toEqual({
    label: 'changed',
    enabled: true,
  });
});
