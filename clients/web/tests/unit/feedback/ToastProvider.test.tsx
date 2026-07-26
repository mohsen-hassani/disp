import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { type ReactElement } from 'react';
import { expect, it } from 'vitest';

import { ToastProvider, useToast } from '../../../src/components/feedback/ToastProvider';

function Trigger({ label, variant }: { label: string; variant?: 'success' | 'error' | 'info' }) {
  const { showToast } = useToast();
  return (
    <button type="button" onClick={() => showToast(label, variant)}>
      Fire {label}
    </button>
  );
}

function renderToasts(children: ReactElement) {
  return render(<ToastProvider>{children}</ToastProvider>);
}

it('shows a toast and dismisses it via the close button', async () => {
  const user = userEvent.setup();
  renderToasts(<Trigger label="Saved." variant="success" />);

  await user.click(screen.getByRole('button', { name: 'Fire Saved.' }));
  expect(await screen.findByText('Saved.')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'Dismiss' }));
  expect(screen.queryByText('Saved.')).not.toBeInTheDocument();
});

// Case: §20.1's "maximum three concurrent; older ones collapse."
it('caps concurrent toasts at three, dropping the oldest', async () => {
  const user = userEvent.setup();
  renderToasts(
    <>
      <Trigger label="One" />
      <Trigger label="Two" />
      <Trigger label="Three" />
      <Trigger label="Four" />
    </>,
  );

  await user.click(screen.getByRole('button', { name: 'Fire One' }));
  await user.click(screen.getByRole('button', { name: 'Fire Two' }));
  await user.click(screen.getByRole('button', { name: 'Fire Three' }));
  await user.click(screen.getByRole('button', { name: 'Fire Four' }));

  expect(screen.queryByText('One')).not.toBeInTheDocument();
  expect(await screen.findByText('Two')).toBeInTheDocument();
  expect(screen.getByText('Three')).toBeInTheDocument();
  expect(screen.getByText('Four')).toBeInTheDocument();
});

// §20.1: "assertive" for errors, "polite" for success/info — Radix
// announces `type="foreground"` toasts (used for `error`) via a hidden
// `aria-live="assertive"` region; `background` toasts (`success`/`info`) get
// `aria-live="polite"`.
it('announces an error toast assertively and a success toast politely', async () => {
  const user = userEvent.setup();
  renderToasts(
    <>
      <Trigger label="Failed." variant="error" />
      <Trigger label="Saved." variant="success" />
    </>,
  );

  await user.click(screen.getByRole('button', { name: 'Fire Failed.' }));
  await user.click(screen.getByRole('button', { name: 'Fire Saved.' }));
  await screen.findAllByText('Failed.');

  // Radix's live-region announcer fills in on the next frame (a screen
  // reader needs the text to change, not just appear, to announce it) —
  // `waitFor` polls with real timers past that one-frame delay.
  await waitFor(() => {
    const assertiveRegions = document.querySelectorAll('[aria-live="assertive"]');
    expect(Array.from(assertiveRegions).some((el) => el.textContent?.includes('Failed.'))).toBe(
      true,
    );
  });
  await waitFor(() => {
    const politeRegions = document.querySelectorAll('[aria-live="polite"]');
    expect(Array.from(politeRegions).some((el) => el.textContent?.includes('Saved.'))).toBe(true);
  });
});
