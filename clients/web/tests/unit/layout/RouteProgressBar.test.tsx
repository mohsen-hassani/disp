import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

// §20.3: only appears after a 150ms delay, so a fast navigation never
// flashes it. Mocking `useRouterState` directly (rather than driving a real
// router navigation) sidesteps this project's documented prior fake-timer/
// router-async interaction flakiness — this component only ever reads one
// boolean out of router state, so that's the only surface worth faking.
const routerState = { isLoading: false };
vi.mock('@tanstack/react-router', () => ({
  useRouterState: ({ select }: { select: (state: { isLoading: boolean }) => boolean }) =>
    select(routerState),
}));

const { RouteProgressBar } = await import('../../../src/components/layout/RouteProgressBar');

afterEach(() => {
  routerState.isLoading = false;
});

it('appears only after the 150ms delay, and disappears once loading ends', async () => {
  const { rerender } = render(<RouteProgressBar />);
  expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();

  routerState.isLoading = true;
  rerender(<RouteProgressBar />);
  expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();

  await waitFor(() => expect(screen.getByRole('progressbar')).toBeInTheDocument(), {
    timeout: 1000,
  });

  routerState.isLoading = false;
  rerender(<RouteProgressBar />);
  await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());
});
