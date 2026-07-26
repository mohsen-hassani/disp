import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import {
  applyResolvedTheme,
  getStoredThemePreference,
  resolveTheme,
  setStoredThemePreference,
  setThemePreference,
} from '../../../src/lib/theme';

const STORAGE_KEY = 'disp.theme';

beforeEach(() => {
  window.localStorage.clear();
});
afterEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
  vi.restoreAllMocks();
});

it('defaults to system with nothing stored, and round-trips a valid stored value', () => {
  expect(getStoredThemePreference()).toBe('system');

  setStoredThemePreference('dark');
  expect(window.localStorage.getItem(STORAGE_KEY)).toBe('dark');
  expect(getStoredThemePreference()).toBe('dark');
});

it('falls back to system for a corrupt/unrecognized stored value', () => {
  window.localStorage.setItem(STORAGE_KEY, 'not-a-real-theme');
  expect(getStoredThemePreference()).toBe('system');
});

it('tolerates localStorage being unavailable', () => {
  const getItemSpy = vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => {
    throw new Error('storage disabled');
  });
  expect(getStoredThemePreference()).toBe('system');
  getItemSpy.mockRestore();

  const setItemSpy = vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
    throw new Error('storage disabled');
  });
  expect(() => setStoredThemePreference('dark')).not.toThrow();
  setItemSpy.mockRestore();
});

it('resolves light/dark literally, and system via prefers-color-scheme', () => {
  expect(resolveTheme('light')).toBe('light');
  expect(resolveTheme('dark')).toBe('dark');

  vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true } as MediaQueryList);
  expect(resolveTheme('system')).toBe('dark');

  vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: false } as MediaQueryList);
  expect(resolveTheme('system')).toBe('light');
});

it('applies the resolved theme to the document element and the theme-color meta tag', () => {
  const meta = document.createElement('meta');
  meta.setAttribute('name', 'theme-color');
  document.head.appendChild(meta);

  applyResolvedTheme('dark');
  expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  expect(meta.getAttribute('content')).toBe('#131519');

  applyResolvedTheme('light');
  expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  expect(meta.getAttribute('content')).toBe('#ffffff');

  meta.remove();
});

it('setThemePreference persists the choice and applies it to the document', () => {
  setThemePreference('dark');
  expect(getStoredThemePreference()).toBe('dark');
  expect(document.documentElement.getAttribute('data-theme')).toBe('dark');

  setThemePreference('light');
  expect(getStoredThemePreference()).toBe('light');
  expect(document.documentElement.getAttribute('data-theme')).toBe('light');
});
