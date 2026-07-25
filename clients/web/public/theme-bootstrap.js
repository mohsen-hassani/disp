// WEB-SPEC §11.3: resolves and applies the theme to <html> before first
// paint, to avoid a flash of the wrong theme. Lives in an external file
// (not inline in index.html) because the production CSP (§24.3) has no
// `'unsafe-inline'` in script-src.
//
// This duplicates (rather than imports) the resolution logic in
// src/lib/theme.ts on purpose: it must run synchronously before the bundled
// app JS — which hasn't loaded yet — so it can't share code with it. Keep
// the two in sync if the storage key or fallback rule ever changes.
(function () {
  var STORAGE_KEY = 'disp.theme';
  var stored = null;
  try {
    stored = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    // localStorage unavailable (private browsing, disabled storage, etc.) —
    // fall through to the prefers-color-scheme default below.
  }

  var resolved =
    stored === 'light' || stored === 'dark'
      ? stored
      : window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light';

  document.documentElement.setAttribute('data-theme', resolved);
})();
