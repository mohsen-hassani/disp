import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import { ToastProvider } from '../../../src/components/feedback/ToastProvider';
import { UpdatePrompt } from '../../../src/pwa/UpdatePrompt';

const updateServiceWorker = vi.fn().mockResolvedValue(undefined);

vi.mock('virtual:pwa-register/react', () => ({
  useRegisterSW: () => ({
    needRefresh: [true, vi.fn()],
    offlineReady: [false, vi.fn()],
    updateServiceWorker,
  }),
}));

// Case 46: a waiting service worker shows the update toast and does not
// auto-reload.
it('shows a persistent toast with a Reload action, and never reloads on its own', async () => {
  const user = userEvent.setup();
  render(
    <ToastProvider>
      <UpdatePrompt />
    </ToastProvider>,
  );

  expect(await screen.findByText('A new version is available.')).toBeInTheDocument();
  expect(updateServiceWorker).not.toHaveBeenCalled();

  await user.click(screen.getByRole('button', { name: /reload/i }));

  expect(updateServiceWorker).toHaveBeenCalledWith(true);
});
