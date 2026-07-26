import { useCallback, useEffect, useState } from 'react';

// §8.1/§17.3: `disp.installDismissedAt` (epoch ms) — the second of exactly
// two permitted localStorage keys, reserved by M03 for exactly this
// purpose (see tests/unit/auth/no-persisted-credential.test.ts's exhaustive
// key list).
const STORAGE_KEY = 'disp.installDismissedAt';
const DISMISS_DAYS = 30;
const DISMISS_MS = DISMISS_DAYS * 24 * 60 * 60 * 1000;

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

function readDismissedAt(): number | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const value = raw ? Number(raw) : NaN;
    return Number.isFinite(value) ? value : null;
  } catch {
    // localStorage unavailable (private browsing, disabled storage, etc.).
    return null;
  }
}

function writeDismissedAt(timestamp: number): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, String(timestamp));
  } catch {
    // Ignore — the dismissal just won't persist across reloads.
  }
}

function isStandalone(): boolean {
  const nav = navigator as Navigator & { standalone?: boolean };
  // `navigator.standalone` is iOS Safari's own (non-standard, pre-`display-mode`) signal.
  return window.matchMedia('(display-mode: standalone)').matches || nav.standalone === true;
}

function isIOSSafari(): boolean {
  return /iPad|iPhone|iPod/.test(navigator.userAgent);
}

function isRecentlyDismissed(): boolean {
  const dismissedAt = readDismissedAt();
  return dismissedAt !== null && Date.now() - dismissedAt < DISMISS_MS;
}

export type InstallPromptVariant = 'android' | 'ios' | null;

export interface UseInstallPromptResult {
  /** `'android'` (or desktop Chromium) has a real native prompt; `'ios'` is a share-sheet hint; `null` shows nothing. */
  variant: InstallPromptVariant;
  /** Only meaningful for `variant === 'android'` — a no-op otherwise. */
  promptInstall: () => void;
  dismiss: () => void;
}

/**
 * §17.3. iOS Safari never fires `beforeinstallprompt` at all, so `variant`
 * distinguishes "we can trigger the native prompt" from "we can only show a
 * manual instruction" — the card (this milestone's own file, `InstallPromptCard.tsx`)
 * renders different copy and controls for each rather than pretending
 * they're the same interaction.
 */
export function useInstallPrompt(): UseInstallPromptResult {
  const [deferredEvent, setDeferredEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [dismissed, setDismissed] = useState(isRecentlyDismissed);

  useEffect(() => {
    function handleBeforeInstallPrompt(event: Event): void {
      event.preventDefault();
      setDeferredEvent(event as BeforeInstallPromptEvent);
    }
    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    return () => window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
  }, []);

  const dismiss = useCallback(() => {
    writeDismissedAt(Date.now());
    setDismissed(true);
  }, []);

  const promptInstall = useCallback(() => {
    if (!deferredEvent) {
      return;
    }
    void deferredEvent.prompt().then(() => setDeferredEvent(null));
  }, [deferredEvent]);

  if (dismissed || isStandalone()) {
    return { variant: null, promptInstall: () => {}, dismiss };
  }
  if (deferredEvent) {
    return { variant: 'android', promptInstall, dismiss };
  }
  if (isIOSSafari()) {
    return { variant: 'ios', promptInstall: () => {}, dismiss };
  }
  return { variant: null, promptInstall: () => {}, dismiss };
}
