import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import { SchemaForm } from '../../../src/components/schema-form/SchemaForm';
import type { JsonSchemaDoc } from '../../../src/components/schema-form/types';

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
  },
};

// Test 28.
it('renders each Appendix B widget type', () => {
  render(<SchemaForm schema={schema} initialValue={{}} onSubmit={vi.fn()} />);
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
  render(<SchemaForm schema={schema} initialValue={{}} onSubmit={onSubmit} />);

  await user.click(screen.getByRole('button', { name: /^save$/i }));

  await waitFor(() => expect(screen.getAllByRole('alert').length).toBeGreaterThan(0));
  expect(onSubmit).not.toHaveBeenCalled();
});

// Test 30.
it('renders an unsupported construct as a disabled fallback field, not a crash', () => {
  render(<SchemaForm schema={schema} initialValue={{}} onSubmit={vi.fn()} />);
  const fallback = screen.getByDisplayValue("This setting can't be edited here.");
  expect(fallback).toBeDisabled();
});

// Test 31.
it('renders a masked secret empty with the Saved badge, and omits it when untouched', async () => {
  const onSubmit = vi.fn();
  const user = userEvent.setup();
  render(
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
  render(
    <SchemaForm schema={schema} initialValue={{ name: 'Ada', token: '***' }} onSubmit={onSubmit} />,
  );

  await user.click(screen.getByRole('button', { name: /clear/i }));
  await user.click(screen.getByRole('button', { name: /^save$/i }));

  await waitFor(() => expect(onSubmit).toHaveBeenCalled());
  const [payload] = onSubmit.mock.calls[0] as [Record<string, unknown>];
  expect(payload.token).toBeNull();
});
