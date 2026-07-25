import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { qk } from '../../../src/api/queryKeys';
import { TokensPage } from '../../../src/routes/-tokens';
import { jsonResponse } from '../auth/testUtils';
import { renderWithProviders } from './testUtils';

beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
});

let fetchSpy: ReturnType<typeof vi.spyOn>;
afterEach(() => {
  fetchSpy?.mockRestore();
});

const EXISTING_TOKEN = {
  id: 'tok-1',
  name: 'CI runner',
  token_prefix: 'disp_pat_ab12',
  created_at: '2026-01-01T00:00:00Z',
  last_used_at: null,
  expires_at: null,
};

function tokensListResponse(tokens: unknown[] = [EXISTING_TOKEN]) {
  return jsonResponse(tokens);
}

it('lists existing tokens with "Never" for null last-used/expires', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(tokensListResponse());
  renderWithProviders(<TokensPage />);

  expect(await screen.findByText('CI runner')).toBeInTheDocument();
  const neverCells = screen.getAllByText('Never');
  expect(neverCells).toHaveLength(2); // last used + expires
});

it('creating a token reveals the plaintext once, dismissible only via "I\'ve saved it"', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(tokensListResponse([]))
    .mockResolvedValueOnce(
      jsonResponse(
        {
          id: 'tok-2',
          name: 'New token',
          token_prefix: 'disp_pat_xy99',
          created_at: '2026-01-02T00:00:00Z',
          last_used_at: null,
          expires_at: null,
          token: 'disp_pat_xy99_the_secret_plaintext',
        },
        { status: 201 },
      ),
    )
    .mockResolvedValueOnce(
      tokensListResponse([{ ...EXISTING_TOKEN, id: 'tok-2', name: 'New token' }]),
    );
  const user = userEvent.setup();
  renderWithProviders(<TokensPage />);
  await screen.findByText('No API tokens yet.');

  await user.click(screen.getByRole('button', { name: /^create token$/i }));
  await user.type(screen.getByLabelText(/^name$/i), 'New token');
  await user.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: /^create token$/i }),
  );

  await waitFor(() =>
    expect(screen.getByText('disp_pat_xy99_the_secret_plaintext')).toBeInTheDocument(),
  );

  // No native way to dismiss besides the explicit button: Escape must not close it.
  await user.keyboard('{Escape}');
  expect(screen.getByText('disp_pat_xy99_the_secret_plaintext')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /i've saved it/i }));
  expect(screen.queryByText('disp_pat_xy99_the_secret_plaintext')).not.toBeInTheDocument();
});

it('never writes the plaintext into the tokens query cache', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(tokensListResponse([]))
    .mockResolvedValueOnce(
      jsonResponse(
        {
          id: 'tok-3',
          name: 'Cache check',
          token_prefix: 'disp_pat_zz00',
          created_at: '2026-01-03T00:00:00Z',
          last_used_at: null,
          expires_at: null,
          token: 'disp_pat_zz00_never_cached',
        },
        { status: 201 },
      ),
    )
    .mockResolvedValueOnce(
      tokensListResponse([
        {
          id: 'tok-3',
          name: 'Cache check',
          token_prefix: 'disp_pat_zz00',
          created_at: '2026-01-03T00:00:00Z',
          last_used_at: null,
          expires_at: null,
        },
      ]),
    );
  const user = userEvent.setup();
  const { queryClient } = renderWithProviders(<TokensPage />);
  await screen.findByText('No API tokens yet.');

  await user.click(screen.getByRole('button', { name: /^create token$/i }));
  await user.type(screen.getByLabelText(/^name$/i), 'Cache check');
  await user.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: /^create token$/i }),
  );
  await screen.findByText('disp_pat_zz00_never_cached');

  await waitFor(() => expect(queryClient.getQueryData(qk.auth.tokens())).toBeDefined());
  const cached = JSON.stringify(queryClient.getQueryData(qk.auth.tokens()));
  expect(cached).not.toContain('disp_pat_zz00_never_cached');
});

it('revoking asks for confirmation naming the specific token', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(tokensListResponse())
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(tokensListResponse([]));
  const user = userEvent.setup();
  renderWithProviders(<TokensPage />);
  await screen.findByText('CI runner');

  await user.click(screen.getByRole('button', { name: /^revoke$/i }));
  expect(screen.getByText(/revoke "ci runner"/i)).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /^revoke token$/i }));
  await waitFor(() => expect(screen.getByText('No API tokens yet.')).toBeInTheDocument());
});
