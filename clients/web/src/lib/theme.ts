import { useSyncExternalStore } from 'react';

// WEB-SPEC §8.1/§11.3. `disp.theme` (not the spec's literal `mystuff.theme`
// — see milestones/client/M01-bootstrap.md's DISP naming section) is one of
// exactly two permitted localStorage keys (§8.1); this file is the only one
// allowed to read or write it.
//
// public/theme-bootstrap.js duplicates the resolution half of this logic —
// it must run before this bundle loads, so it can't import from here. Keep
// the two in sync if the storage key or fallback rule ever changes.
//
// The runtime store/hook below (M04) is a plain module-scoped external
// store, matching src/auth/authState.ts's pattern, rather than a React
// Context — nothing here needs a Provider component, and a bare hook is one
// less thing main.tsx has to wrap the tree in.

export type ThemePreference = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'disp.theme';

export function getStoredThemePreference(): ThemePreference {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (value === 'light' || value === 'dark' || value === 'system') {
      return value;
    }
  } catch {
    // localStorage unavailable (private browsing, disabled storage, etc.).
  }
  return 'system';
}

export function setStoredThemePreference(preference: ThemePreference): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, preference);
  } catch {
    // Ignore — the preference just won't persist across reloads.
  }
}

function prefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  return preference === 'system' ? (prefersDark() ? 'dark' : 'light') : preference;
}

// Appendix C surface colors, kept in sync with src/styles/index.css.
const THEME_COLOR: Record<ResolvedTheme, string> = {
  light: '#ffffff',
  dark: '#131519',
};

export function applyResolvedTheme(resolved: ResolvedTheme): void {
  document.documentElement.setAttribute('data-theme', resolved);
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', THEME_COLOR[resolved]);
}

export interface ThemeStoreState {
  preference: ThemePreference;
  resolved: ResolvedTheme;
}

let preference = getStoredThemePreference();
let snapshot: ThemeStoreState = { preference, resolved: resolveTheme(preference) };
const listeners = new Set<() => void>();

// index.html's inline script already set data-theme before first paint; this
// call is what keeps <meta name="theme-color"> (which that script can't
// touch without duplicating THEME_COLOR too) in sync on every load.
applyResolvedTheme(snapshot.resolved);

function commit(next: ThemeStoreState): void {
  snapshot = next;
  applyResolvedTheme(next.resolved);
  for (const listener of listeners) {
    listener();
  }
}

/** The user menu's Theme submenu (§12.4) calls this. */
export function setThemePreference(next: ThemePreference): void {
  preference = next;
  setStoredThemePreference(next);
  commit({ preference: next, resolved: resolveTheme(next) });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): ThemeStoreState {
  return snapshot;
}

if (typeof window !== 'undefined' && window.matchMedia) {
  // Only `system` preference needs to react to the OS-level change — an
  // explicit light/dark choice is intentionally sticky.
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (preference === 'system') {
      commit({ preference, resolved: resolveTheme(preference) });
    }
  });
}

export function useTheme(): ThemeStoreState & { setPreference: typeof setThemePreference } {
  const state = useSyncExternalStore(subscribe, getSnapshot);
  return { ...state, setPreference: setThemePreference };
}
