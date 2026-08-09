import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { TileActionDialog } from '../../../src/components/tiles/TileActionDialog';
import { makeTileAction } from './fixtures';
import { renderTile } from './testUtils';

beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
});

let fetchSpy: ReturnType<typeof vi.spyOn> | undefined;
afterEach(() => {
  fetchSpy?.mockRestore();
  fetchSpy = undefined;
});

const schemaAction = makeTileAction({
  label: 'Quick add',
  method: 'POST',
  path: '/api/notes',
  body_schema: {
    type: 'object',
    properties: { body: { type: 'string', title: 'Body' } },
    required: ['body'],
  },
});

// Test 21.
it('opens with fields matching the body_schema', async () => {
  await renderTile(
    <TileActionDialog action={schemaAction} tileKey="demo.tile" open onOpenChange={() => {}} />,
  );
  expect(screen.getByLabelText(/^Body/)).toBeInTheDocument();
});

// Test 23.
it('keeps the dialog open with an inline error and preserved input on a failing submit', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        type: 'about:blank',
        title: 'Server error',
        status: 500,
        detail: 'boom',
        instance: '/api/notes',
        code: 'core.platform.internal_error',
        request_id: 'req-2',
      }),
      { status: 500, headers: { 'Content-Type': 'application/json' } },
    ),
  );
  const user = userEvent.setup();
  await renderTile(
    <TileActionDialog action={schemaAction} tileKey="demo.tile" open onOpenChange={() => {}} />,
  );

  await user.type(screen.getByLabelText(/^Body/), 'hello world');
  await user.click(screen.getByRole('button', { name: /^quick add$/i }));

  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/req-2/));
  expect(screen.getByLabelText(/^Body/)).toHaveValue('hello world');
  // Still mounted (didn't close) — the dialog title is the clearest proof.
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

// Test 34 (this dialog's slice): M10 fixed a real regression here — a 422
// used to be swallowed by describeActionError() instead of mapped to its
// field, unlike every other §19.3 consumer (ShareDialog, NoteEditor).
it('maps a 422 error to its field via the shared §19.3 mapper', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        type: 'about:blank',
        title: 'Validation error',
        status: 422,
        detail: 'Invalid input.',
        instance: '/api/notes',
        code: 'core.platform.validation_error',
        request_id: 'req-3',
        errors: [{ loc: ['body', 'body'], msg: 'Body is too long.' }],
      }),
      { status: 422, headers: { 'Content-Type': 'application/json' } },
    ),
  );
  const user = userEvent.setup();
  await renderTile(
    <TileActionDialog action={schemaAction} tileKey="demo.tile" open onOpenChange={() => {}} />,
  );

  await user.type(screen.getByLabelText(/^Body/), 'hello world');
  await user.click(screen.getByRole('button', { name: /^quick add$/i }));

  await waitFor(() => expect(screen.getByText('Body is too long.')).toBeInTheDocument());
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});
