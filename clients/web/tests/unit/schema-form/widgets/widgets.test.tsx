import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import { SchemaForm } from '../../../../src/components/schema-form/SchemaForm';
import type { JsonSchemaDoc } from '../../../../src/components/schema-form/types';
import { renderWithRouter } from '../testUtils';

// Appendix B's array row: string items get a repeatable text input; the
// widget's Add/Remove buttons are the only way to grow/shrink it.
it('ArrayWidget (string items): add appends a row, remove drops it, and both submit', async () => {
  const schema: JsonSchemaDoc = {
    type: 'object',
    properties: { tags: { type: 'array', items: { type: 'string' }, title: 'Tags' } },
  };
  const onSubmit = vi.fn();
  const user = userEvent.setup();
  await renderWithRouter(<SchemaForm schema={schema} initialValue={{}} onSubmit={onSubmit} />);

  await user.click(screen.getByRole('button', { name: /^add$/i }));
  await user.type(screen.getByLabelText('Item 1'), 'urgent');
  await user.click(screen.getByRole('button', { name: /^add$/i }));
  await user.type(screen.getByLabelText('Item 2'), 'later');

  await user.click(screen.getByRole('button', { name: /remove item 1/i }));
  expect(screen.queryByDisplayValue('urgent')).not.toBeInTheDocument();
  expect(screen.getByDisplayValue('later')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /^save$/i }));
  await waitFor(() => expect(onSubmit).toHaveBeenCalled());
  expect((onSubmit.mock.calls[0] as [Record<string, unknown>])[0]).toEqual({ tags: ['later'] });
});

// Appendix B's other array row: object items render each nested field via FieldFor.
it('ArrayWidget (object items): a new row renders its nested fields', async () => {
  const schema: JsonSchemaDoc = {
    type: 'object',
    properties: {
      rows: {
        type: 'array',
        title: 'Rows',
        items: {
          type: 'object',
          properties: { label: { type: 'string', title: 'Label' } },
        },
      },
    },
  };
  const user = userEvent.setup();
  await renderWithRouter(<SchemaForm schema={schema} initialValue={{}} onSubmit={vi.fn()} />);

  await user.click(screen.getByRole('button', { name: /^add$/i }));
  expect(screen.getByLabelText('Label')).toBeInTheDocument();
});

it('EnumWidget renders a radiogroup for <=3 options and lets one be chosen', async () => {
  const schema: JsonSchemaDoc = {
    type: 'object',
    properties: { color: { type: 'string', title: 'Color', enum: ['red', 'green', 'blue'] } },
  };
  const user = userEvent.setup();
  await renderWithRouter(<SchemaForm schema={schema} initialValue={{}} onSubmit={vi.fn()} />);

  const group = screen.getByRole('radiogroup');
  await user.click(within(group).getByRole('radio', { name: 'green' }));
  expect(within(group).getByRole('radio', { name: 'green' })).toBeChecked();
});

it('EnumWidget renders a select once there are more than 3 options', async () => {
  const schema: JsonSchemaDoc = {
    type: 'object',
    properties: {
      color: { type: 'string', title: 'Color', enum: ['red', 'green', 'blue', 'yellow'] },
    },
  };
  const user = userEvent.setup();
  await renderWithRouter(<SchemaForm schema={schema} initialValue={{}} onSubmit={vi.fn()} />);

  await user.selectOptions(screen.getByLabelText('Color'), 'yellow');
  expect(screen.getByLabelText('Color')).toHaveValue('yellow');
});

it('StringWidget switches to a textarea once maxLength exceeds 200', async () => {
  const schema: JsonSchemaDoc = {
    type: 'object',
    properties: { bio: { type: 'string', title: 'Bio', maxLength: 500 } },
  };
  await renderWithRouter(<SchemaForm schema={schema} initialValue={{}} onSubmit={vi.fn()} />);
  expect(screen.getByLabelText('Bio').tagName).toBe('TEXTAREA');
});

it('humanizes a field name into its label when the schema has no title', async () => {
  const schema: JsonSchemaDoc = {
    type: 'object',
    properties: { displayName: { type: 'string' } },
  };
  await renderWithRouter(<SchemaForm schema={schema} initialValue={{}} onSubmit={vi.fn()} />);
  expect(screen.getByLabelText('Display Name')).toBeInTheDocument();
});

it('falls back to the disabled placeholder for an array with no items schema', async () => {
  const schema: JsonSchemaDoc = {
    type: 'object',
    properties: { anything: { type: 'array', title: 'Anything' } },
  };
  await renderWithRouter(<SchemaForm schema={schema} initialValue={{}} onSubmit={vi.fn()} />);
  expect(screen.getByLabelText('Anything')).toBeDisabled();
});

it('renders NumberWidget for a plain (non-integer) number field', async () => {
  const schema: JsonSchemaDoc = {
    type: 'object',
    properties: { price: { type: 'number', title: 'Price' } },
  };
  await renderWithRouter(<SchemaForm schema={schema} initialValue={{}} onSubmit={vi.fn()} />);
  expect(screen.getByLabelText('Price')).toHaveAttribute('type', 'number');
});

it('falls back to the disabled placeholder for a schema type outside Appendix B', async () => {
  const schema: JsonSchemaDoc = {
    type: 'object',
    properties: { mystery: { title: 'Mystery' } },
  };
  await renderWithRouter(<SchemaForm schema={schema} initialValue={{}} onSubmit={vi.fn()} />);
  expect(screen.getByLabelText('Mystery')).toBeDisabled();
});

it('StringWidget maps format to the matching native input type', async () => {
  const schema: JsonSchemaDoc = {
    type: 'object',
    properties: {
      email: { type: 'string', title: 'Email', format: 'email' },
      site: { type: 'string', title: 'Site', format: 'uri' },
      when: { type: 'string', title: 'When', format: 'date-time' },
      plain: { type: 'string', title: 'Plain' },
    },
  };
  await renderWithRouter(<SchemaForm schema={schema} initialValue={{}} onSubmit={vi.fn()} />);

  expect(screen.getByLabelText('Email')).toHaveAttribute('type', 'email');
  expect(screen.getByLabelText('Site')).toHaveAttribute('type', 'url');
  expect(screen.getByLabelText('When')).toHaveAttribute('type', 'datetime-local');
  expect(screen.getByLabelText('Plain')).toHaveAttribute('type', 'text');
});
