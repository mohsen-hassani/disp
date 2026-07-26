import type { ReactElement } from 'react';

import { cn } from '../../lib/cn';

interface SpinnerProps {
  className?: string;
}

// §20.3's button loading indicator — a leading icon in either state (a
// transparent placeholder when idle, spinning when submitting) so a
// button's width never changes between the two.
export function Spinner({ className }: SpinnerProps): ReactElement {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      className={cn('h-4 w-4 shrink-0 animate-spin motion-reduce:animate-none', className)}
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path
        d="M22 12a10 10 0 0 0-10-10"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}
