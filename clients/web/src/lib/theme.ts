// WEB-SPEC §8.1/§11.3. `disp.theme` (not the spec's literal `mystuff.theme`
// — see milestones/client/M01-bootstrap.md's DISP naming section) is one of
// exactly two permitted localStorage keys (§8.1); this file is the only one
// allowed to read or write it.
//
// public/theme-bootstrap.js duplicates the resolution half of this logic —
// it must run before this bundle loads, so it can't import from here. Keep
// the two in sync if the storage key or fallback rule ever changes.
//
// The runtime UI (a theme context/hook, the user menu's Theme submenu) is
// M04's job; this module only provides the underlying primitives.

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
