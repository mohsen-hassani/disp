import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { useInstallPrompt } from '../../../src/hooks/useInstallPrompt';

const STORAGE_KEY = 'disp.installDismissedAt';
const DAY_MS = 24 * 60 * 60 * 1000;

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

let userAgentSpy: ReturnType<typeof vi.spyOn> | undefined;
let matchMediaSpy: ReturnType<typeof vi.spyOn> | undefined;

function setStandalone(standalone: boolean): void {
  matchMediaSpy?.mockRestore();
  matchMediaSpy = vi.spyOn(window, 'matchMedia').mockReturnValue({
    matches: standalone,
  } as MediaQueryList);
}

function setIOS(isIOS: boolean): void {
  userAgentSpy?.mockRestore();
  userAgentSpy = vi
    .spyOn(window.navigator, 'userAgent', 'get')
    .mockReturnValue(
      isIOS
        ? 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)'
        : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    );
}

beforeEach(() => {
  window.localStorage.clear();
  setStandalone(false);
  setIOS(false);
});

afterEach(() => {
  userAgentSpy?.mockRestore();
  matchMediaSpy?.mockRestore();
  window.localStorage.clear();
});

it('is null until beforeinstallprompt fires, then android once captured', () => {
  const { result } = renderHook(() => useInstallPrompt());
  expect(result.current.variant).toBeNull();

  fireBeforeInstallPrompt();
  expect(result.current.variant).toBe('android');
});

it("promptInstall calls the captured event's prompt()", () => {
  const { result } = renderHook(() => useInstallPrompt());
  const { prompt } = fireBeforeInstallPrompt();

  act(() => result.current.promptInstall());

  expect(prompt).toHaveBeenCalledTimes(1);
});

it('dismiss writes disp.installDismissedAt and hides the card', () => {
  const { result } = renderHook(() => useInstallPrompt());
  fireBeforeInstallPrompt();
  expect(result.current.variant).toBe('android');

  act(() => result.current.dismiss());

  expect(result.current.variant).toBeNull();
  expect(window.localStorage.getItem(STORAGE_KEY)).not.toBeNull();
});

it('stays hidden within the 30-day dismissal window, reappears after', () => {
  window.localStorage.setItem(STORAGE_KEY, String(Date.now() - 10 * DAY_MS));
  const { result: recentlyDismissed } = renderHook(() => useInstallPrompt());
  fireBeforeInstallPrompt();
  expect(recentlyDismissed.current.variant).toBeNull();

  window.localStorage.setItem(STORAGE_KEY, String(Date.now() - 31 * DAY_MS));
  const { result: expiredDismissal } = renderHook(() => useInstallPrompt());
  fireBeforeInstallPrompt();
  expect(expiredDismissal.current.variant).toBe('android');
});

it('shows nothing while already standalone, even with a captured event', () => {
  setStandalone(true);
  const { result } = renderHook(() => useInstallPrompt());
  fireBeforeInstallPrompt();

  expect(result.current.variant).toBeNull();
});

it('shows the ios hint on iOS Safari, which never fires beforeinstallprompt', () => {
  setIOS(true);
  const { result } = renderHook(() => useInstallPrompt());

  expect(result.current.variant).toBe('ios');
});
