import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import { SchemaForm } from '../../../src/components/schema-form/SchemaForm';
import type { JsonSchemaDoc } from '../../../src/components/schema-form/types';
import { renderWithRouter } from './testUtils';

const schema: JsonSchemaDoc = {
  type: 'object',
  required: ['name'],
  properties: {
    name: { type: 'string', title: 'Name' },
    age: { type: 'integer', title: 'Age' },
    active: { type: 'boolean', title: 'Active' },
    color: { type: 'string', title: 'Color', enum: ['red', 'green', 'blue', 'yellow'] },
    address: {
      type: 'object',
      title: 'Address',
      properties: { city: { type: 'string', title: 'City' } },
    },
    // Not in Appendix B's exhaustive array table (only string/object items
    // are) — must render the disabled fallback, not a text-row array.
    weird: { type: 'array', items: { type: 'integer' }, title: 'Weird' },
    token: { type: 'string', title: 'Token', 'x-secret': true },
    // A non-string x-secret field (confirmed live against `core.notifier`'s
    // `urls: dict[str, str]`) — must also fall back, not bind a dict to a
    // password input.
    urls: { type: 'object', title: 'Urls', 'x-secret': true },
  },
};

// Test 28.
it('renders each Appendix B widget type', async () => {
  await renderWithRouter(<SchemaForm schema={schema} initialValue={{}} onSubmit={vi.fn()} />);
  expect(screen.getByLabelText(/^Name/)).toBeInTheDocument();
  expect(screen.getByLabelText('Age')).toHaveAttribute('type', 'number');
  expect(screen.getByRole('switch')).toBeInTheDocument();
  expect(screen.getByLabelText('City')).toBeInTheDocument();
  expect(screen.getByLabelText('Color').tagName).toBe('SELECT');
});

// Test 29.
it('marks required fields and blocks submit when they are empty', async () => {
  const onSubmit = vi.fn();
  const user = userEvent.setup();
  await renderWithRouter(<SchemaForm schema={schema} initialValue={{}} onSubmit={onSubmit} />);

  await user.click(screen.getByRole('button', { name: /^save$/i }));

  await waitFor(() => expect(screen.getAllByRole('alert').length).toBeGreaterThan(0));
  expect(onSubmit).not.toHaveBeenCalled();
});

// Test 30.
it('renders an unsupported construct as a disabled fallback field, not a crash', async () => {
  await renderWithRouter(<SchemaForm schema={schema} initialValue={{}} onSubmit={vi.fn()} />);
  // Both `weird` (unsupported array items) and `urls` (a non-string
  // x-secret field) land here.
  const fallbacks = screen.getAllByDisplayValue("This setting can't be edited here.");
  expect(fallbacks).toHaveLength(2);
  for (const fallback of fallbacks) {
    expect(fallback).toBeDisabled();
  }
});

// Test 31.
it('renders a masked secret empty with the Saved badge, and omits it when untouched', async () => {
  const onSubmit = vi.fn();
  const user = userEvent.setup();
  await renderWithRouter(
    <SchemaForm schema={schema} initialValue={{ name: 'Ada', token: '***' }} onSubmit={onSubmit} />,
  );

  expect(screen.getByText('Set')).toBeInTheDocument();
  expect(screen.getByLabelText('Token')).toHaveValue('');

  await user.click(screen.getByRole('button', { name: /^save$/i }));

  await waitFor(() => expect(onSubmit).toHaveBeenCalled());
  const [payload] = onSubmit.mock.calls[0] as [Record<string, unknown>];
  expect(payload).not.toHaveProperty('token');
});

// Test 32.
it('a secret cleared via the Clear button sends null', async () => {
  const onSubmit = vi.fn();
  const user = userEvent.setup();
  await renderWithRouter(
    <SchemaForm schema={schema} initialValue={{ name: 'Ada', token: '***' }} onSubmit={onSubmit} />,
  );

  await user.click(screen.getByRole('button', { name: /clear/i }));
  await user.click(screen.getByRole('button', { name: /^save$/i }));

  await waitFor(() => expect(onSubmit).toHaveBeenCalled());
  const [payload] = onSubmit.mock.calls[0] as [Record<string, unknown>];
  expect(payload.token).toBeNull();
});

// Test 33: only changed keys appear in what SchemaForm hands the caller —
// verified via `dirtyFields`, which is what the settings screen filters by.
it('reports dirtyFields covering only the fields the user actually touched', async () => {
  const onSubmit = vi.fn();
  const user = userEvent.setup();
  await renderWithRouter(
    <SchemaForm schema={schema} initialValue={{ name: 'Ada', age: 30 }} onSubmit={onSubmit} />,
  );

  await user.clear(screen.getByLabelText(/^Name/));
  await user.type(screen.getByLabelText(/^Name/), 'Grace');
  await user.click(screen.getByRole('button', { name: /^save$/i }));

  await waitFor(() => expect(onSubmit).toHaveBeenCalled());
  const [, dirtyFields] = onSubmit.mock.calls[0] as [
    Record<string, unknown>,
    Record<string, unknown>,
  ];
  expect(dirtyFields).toHaveProperty('name');
  expect(dirtyFields).not.toHaveProperty('age');
});

// Test 34.
it('maps a 422 error to its field, and an unmapped one to the form-level region', async () => {
  await renderWithRouter(
    <SchemaForm
      schema={schema}
      initialValue={{ name: 'Ada' }}
      onSubmit={vi.fn()}
      serverErrors={[
        { loc: ['body', 'name'], msg: 'That name is already taken.' },
        { loc: ['body', 'nonexistent_field'], msg: 'Unmappable server complaint.' },
      ]}
    />,
  );

  await waitFor(() => expect(screen.getByText('That name is already taken.')).toBeInTheDocument());
  expect(screen.getByText('Unmappable server complaint.')).toBeInTheDocument();
});

// §14.3 rule 7.
it('warns before navigating away with unsaved changes', async () => {
  const user = userEvent.setup();
  const { router } = await renderWithRouter(
    <SchemaForm schema={schema} initialValue={{ name: 'Ada' }} onSubmit={vi.fn()} />,
  );

  await user.clear(screen.getByLabelText(/^Name/));
  await user.type(screen.getByLabelText(/^Name/), 'Grace');
  // `useBlocker` hooks into the router's own history object — a raw
  // `window.history.pushState` (bypassing that history instance entirely,
  // and this test's router uses an in-memory one regardless) wouldn't
  // trigger it.
  void router.history.push('/somewhere-else');

  await screen.findByRole('dialog');
  expect(screen.getByText(/leave without saving/i)).toBeInTheDocument();
});

it('"Stay" closes the unsaved-changes dialog without navigating away', async () => {
  const user = userEvent.setup();
  const { router } = await renderWithRouter(
    <SchemaForm schema={schema} initialValue={{ name: 'Ada' }} onSubmit={vi.fn()} />,
  );

  await user.clear(screen.getByLabelText(/^Name/));
  await user.type(screen.getByLabelText(/^Name/), 'Grace');
  void router.history.push('/somewhere-else');
  await screen.findByRole('dialog');

  await user.click(screen.getByRole('button', { name: /^stay$/i }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(router.history.location.pathname).toBe('/');
});

it('"Leave" proceeds with the navigation', async () => {
  const user = userEvent.setup();
  const { router } = await renderWithRouter(
    <SchemaForm schema={schema} initialValue={{ name: 'Ada' }} onSubmit={vi.fn()} />,
  );

  await user.clear(screen.getByLabelText(/^Name/));
  await user.type(screen.getByLabelText(/^Name/), 'Grace');
  void router.history.push('/somewhere-else');
  await screen.findByRole('dialog');

  await user.click(screen.getByRole('button', { name: /^leave$/i }));
  await waitFor(() => expect(router.history.location.pathname).toBe('/somewhere-else'));
});

it('seeds a field with its schema default when absent from initialValue', async () => {
  const schemaWithDefault: JsonSchemaDoc = {
    type: 'object',
    properties: { name: { type: 'string', title: 'Name', default: 'Ada' } },
  };
  await renderWithRouter(
    <SchemaForm schema={schemaWithDefault} initialValue={{}} onSubmit={vi.fn()} />,
  );
  expect(screen.getByLabelText('Name')).toHaveValue('Ada');
});
