import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import { ErrorBoundary } from '../../../src/components/feedback/ErrorBoundary';
import { RootErrorFallback } from '../../../src/components/feedback/RootErrorFallback';
import { RouteErrorFallback } from '../../../src/components/feedback/RouteErrorFallback';

function Bomb(): never {
  throw new Error('boom');
}

it('renders the fallback and logs to console.error on a caught render crash', () => {
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

  render(
    <ErrorBoundary fallback={<RootErrorFallback />}>
      <Bomb />
    </ErrorBoundary>,
  );

  expect(screen.getByText('Something went wrong.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
  expect(screen.getByText(/^Version /)).toBeInTheDocument();
  expect(consoleError).toHaveBeenCalledWith(expect.any(Error));

  consoleError.mockRestore();
});

it('RouteErrorFallback keeps the shell usable and its Retry button calls reset', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  const user = userEvent.setup();
  const reset = vi.fn();

  render(
    <div>
      <nav aria-label="Main">Still here</nav>
      <RouteErrorFallback error={new Error('boom')} reset={reset} info={{ componentStack: '' }} />
    </div>,
  );

  expect(screen.getByText('Still here')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Retry' }));
  expect(reset).toHaveBeenCalledTimes(1);

  vi.restoreAllMocks();
});
