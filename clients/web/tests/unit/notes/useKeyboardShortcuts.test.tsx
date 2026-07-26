import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import { useKeyboardShortcuts } from '../../../src/hooks/useKeyboardShortcuts';
import { renderNotes } from './testUtils';

function Harness({
  onOpenCreateNote,
  onOpenShortcuts,
}: {
  onOpenCreateNote: () => void;
  onOpenShortcuts: () => void;
}) {
  useKeyboardShortcuts({ onOpenCreateNote, onOpenShortcuts });
  return <input aria-label="Some other field" />;
}

it('n opens the create-note dialog when no input has focus', async () => {
  const onOpenCreateNote = vi.fn();
  const user = userEvent.setup();
  await renderNotes(<Harness onOpenCreateNote={onOpenCreateNote} onOpenShortcuts={vi.fn()} />);

  await user.keyboard('n');

  expect(onOpenCreateNote).toHaveBeenCalledTimes(1);
});

it('does not fire when a text input has focus', async () => {
  const onOpenCreateNote = vi.fn();
  const user = userEvent.setup();
  await renderNotes(<Harness onOpenCreateNote={onOpenCreateNote} onOpenShortcuts={vi.fn()} />);

  await user.click(screen.getByLabelText('Some other field'));
  await user.keyboard('n');

  expect(onOpenCreateNote).not.toHaveBeenCalled();
});

it('? opens the shortcuts dialog', async () => {
  const onOpenShortcuts = vi.fn();
  const user = userEvent.setup();
  await renderNotes(<Harness onOpenCreateNote={vi.fn()} onOpenShortcuts={onOpenShortcuts} />);

  await user.keyboard('?');

  expect(onOpenShortcuts).toHaveBeenCalledTimes(1);
});

it('g then d navigates to the dashboard', async () => {
  const user = userEvent.setup();
  const { router } = await renderNotes(
    <Harness onOpenCreateNote={vi.fn()} onOpenShortcuts={vi.fn()} />,
  );
  void router.navigate({ to: '/notes' });
  await waitFor(() => expect(router.state.location.pathname).toBe('/notes'));

  await user.keyboard('g');
  await user.keyboard('d');

  await waitFor(() => expect(router.state.location.pathname).toBe('/'));
});

it('g then n navigates to notes', async () => {
  const user = userEvent.setup();
  const { router } = await renderNotes(
    <Harness onOpenCreateNote={vi.fn()} onOpenShortcuts={vi.fn()} />,
  );

  await user.keyboard('g');
  await user.keyboard('n');

  await waitFor(() => expect(router.state.location.pathname).toBe('/notes'));
});
