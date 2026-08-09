/**
 * Shared by the footer's action `<button>`s and its nav `<Link>`. They sit
 * side by side in the same row, so the styling has to live in one place —
 * two copies of this string would drift the moment either is touched.
 */
export const tileButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
