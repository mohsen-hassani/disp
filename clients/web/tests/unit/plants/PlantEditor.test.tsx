import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import { PlantEditor } from '../../../src/components/plants/PlantEditor';

it('requires a name before submitting', async () => {
  const onSubmit = vi.fn();
  const user = userEvent.setup();
  render(<PlantEditor mode="create" submitting={false} onSubmit={onSubmit} onCancel={vi.fn()} />);

  await user.click(screen.getByRole('button', { name: /create plant/i }));

  expect(await screen.findByText('Name is required')).toBeInTheDocument();
  expect(onSubmit).not.toHaveBeenCalled();
});

it('submits name, description and care notes', async () => {
  const onSubmit = vi.fn();
  const user = userEvent.setup();
  render(<PlantEditor mode="create" submitting={false} onSubmit={onSubmit} onCancel={vi.fn()} />);

  await user.type(screen.getByLabelText(/^name/i), 'Monstera');
  await user.type(screen.getByLabelText(/description/i), 'A big leafy one.');
  await user.type(screen.getByLabelText(/care notes/i), 'Bright indirect light.');
  await user.click(screen.getByRole('button', { name: /create plant/i }));

  await waitFor(() =>
    expect(onSubmit).toHaveBeenCalledWith({
      name: 'Monstera',
      description: 'A big leafy one.',
      care_notes: 'Bright indirect light.',
    }),
  );
});

it('cancels immediately when the form is untouched', async () => {
  const onCancel = vi.fn();
  const user = userEvent.setup();
  render(
    <PlantEditor
      mode="edit"
      initialName="Monstera"
      submitting={false}
      onSubmit={vi.fn()}
      onCancel={onCancel}
    />,
  );

  await user.click(screen.getByRole('button', { name: /^cancel$/i }));
  expect(onCancel).toHaveBeenCalled();
});

it('confirms before discarding a dirty edit form', async () => {
  const onCancel = vi.fn();
  const user = userEvent.setup();
  render(
    <PlantEditor
      mode="edit"
      initialName="Monstera"
      submitting={false}
      onSubmit={vi.fn()}
      onCancel={onCancel}
    />,
  );

  await user.type(screen.getByLabelText(/^name/i), ' variegata');
  await user.click(screen.getByRole('button', { name: /^cancel$/i }));

  expect(await screen.findByRole('dialog')).toBeInTheDocument();
  expect(onCancel).not.toHaveBeenCalled();

  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: /discard/i }));
  expect(onCancel).toHaveBeenCalled();
});

it('surfaces server field errors and an unmapped error message', async () => {
  render(
    <PlantEditor
      mode="create"
      submitting={false}
      onSubmit={vi.fn()}
      onCancel={vi.fn()}
      serverErrors={[
        { loc: ['body', 'name'], msg: 'Name already used.' },
        { loc: ['body', 'unknown_field'], msg: 'Something odd.' },
      ]}
    />,
  );

  expect(await screen.findByText('Name already used.')).toBeInTheDocument();
  expect(screen.getByText('Something odd.')).toBeInTheDocument();
});
