// The same button/field classes the notes screens declare inline. Collected
// once here because the plants screens need them across six files, where
// re-declaring per file would guarantee they drift apart.

export const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

export const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

export const dangerButtonClass =
  'text-danger border-border focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

export const inputClass =
  'border-border bg-surface text-text focus-visible:outline-accent w-full rounded-sm border px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2';

export const labelClass = 'text-text mb-1 block text-sm font-medium';

export const cardClass = 'border-border bg-surface rounded-md border p-4';
