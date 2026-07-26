import type { ReactElement, ReactNode } from 'react';

import { cn } from '../../lib/cn';
import { Spinner } from './Spinner';

interface SubmitButtonProps {
  submitting: boolean;
  disabled?: boolean;
  children: ReactNode;
  className: string;
}

// §20.3: "an inline spinner replacing the label's leading icon, with the
// label retained. The button width MUST NOT change." The spinner's slot is
// always in the layout (just invisible when idle) rather than conditionally
// rendered, which is what actually keeps the width constant — a
// conditionally-rendered icon would still shift the label over by its width.
export function SubmitButton({
  submitting,
  disabled,
  children,
  className,
}: SubmitButtonProps): ReactElement {
  return (
    <button
      type="submit"
      disabled={disabled || submitting}
      className={cn('inline-flex items-center justify-center gap-2', className)}
    >
      <Spinner className={submitting ? undefined : 'invisible'} />
      {children}
    </button>
  );
}
