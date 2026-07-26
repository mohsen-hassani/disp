import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { InstallPromptCard } from '../../../src/pwa/InstallPromptCard';

function fireBeforeInstallPrompt(): { prompt: ReturnType<typeof vi.fn> } {
  const promptFn = vi.fn().mockResolvedValue(undefined);
  const event = new Event('beforeinstallprompt', { cancelable: true }) as Event & {
    prompt: typeof promptFn;
    userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
  };
  event.prompt = promptFn;
  event.userChoice = Promise.resolve({ outcome: 'accepted' });
  act(() => window.dispatchEvent(event));
  return { prompt: promptFn };
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
});

it('renders nothing until a prompt is available', () => {
  render(<InstallPromptCard />);

  expect(screen.queryByText(/install disp/i)).not.toBeInTheDocument();
});

it('shows an Install button once beforeinstallprompt fires, and triggers the real prompt', async () => {
  const user = userEvent.setup();
  render(<InstallPromptCard />);
  const { prompt } = fireBeforeInstallPrompt();

  const installButton = await screen.findByRole('button', { name: /^install$/i });
  await user.click(installButton);

  expect(prompt).toHaveBeenCalledTimes(1);
});

it('dismissing hides the card', async () => {
  const user = userEvent.setup();
  render(<InstallPromptCard />);
  fireBeforeInstallPrompt();
  await screen.findByRole('button', { name: /^install$/i });

  await user.click(screen.getByRole('button', { name: /dismiss install prompt/i }));

  expect(screen.queryByText(/install disp/i)).not.toBeInTheDocument();
});
