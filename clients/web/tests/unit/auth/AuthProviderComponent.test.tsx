import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { AuthProvider } from '../../../src/auth/AuthProvider';
import { client } from '../../../src/api/client';
import { getAuthState, setAuthState } from '../../../src/auth/authState';
import { clearToken } from '../../../src/auth/tokenStore';
import { loginResponse, meResponse, TEST_USER } from './testUtils';

beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
});

let fetchSpy: ReturnType<typeof vi.spyOn>;
afterEach(() => {
  fetchSpy?.mockRestore();
  setAuthState({ status: 'loading' });
  clearToken();
});

function App() {
  return (
    <AuthProvider>
      <p>App content</p>
    </AuthProvider>
  );
}

// §8.3 step 1: a full-page skeleton while bootstrapping — never a flash of
// the login screen or the real app shell.
it('renders a loading skeleton, then the children once bootstrap resolves', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(loginResponse())
    .mockResolvedValueOnce(meResponse());
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );

  expect(screen.getByText('Loading…')).toBeInTheDocument();
  expect(screen.queryByText('App content')).not.toBeInTheDocument();

  await waitFor(() => expect(screen.getByText('App content')).toBeInTheDocument());
  expect(getAuthState()).toMatchObject({ status: 'authenticated' });
});

// §15.1: bootstrap's successful-refresh path seeds ['auth','me'] with the
// full MeResponse it already has, so the account screen never has to
// refetch it separately.
it('seeds the auth/me query cache via onMeFetched during bootstrap', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(loginResponse())
    .mockResolvedValueOnce(meResponse());
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  function Probe() {
    const qc = useQueryClient();
    const cached = qc.getQueryData(['auth', 'me']);
    return <p>{cached ? 'seeded' : 'empty'}</p>;
  }

  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByText('seeded')).toBeInTheDocument());
});

it('falls back to cached-user offline mode via getCachedUser', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('Failed to fetch'));
  const onlineSpy = vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider getCachedUser={() => TEST_USER}>
        <p>App content</p>
      </AuthProvider>
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByText('App content')).toBeInTheDocument());
  expect(getAuthState()).toEqual({ status: 'authenticated', user: TEST_USER });
  onlineSpy.mockRestore();
});
