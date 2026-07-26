import { useRouterState } from '@tanstack/react-router';
import { type ReactElement, useEffect, useState } from 'react';

// WEB-SPEC §20.3: a 2px indeterminate bar under the top bar, appearing only
// after 150ms so a fast navigation never flashes it.
const APPEAR_DELAY_MS = 150;

export function RouteProgressBar(): ReactElement | null {
  const isLoading = useRouterState({ select: (state) => state.isLoading });
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!isLoading) {
      setVisible(false);
      return undefined;
    }
    const timer = window.setTimeout(() => setVisible(true), APPEAR_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [isLoading]);

  if (!visible) {
    return null;
  }

  return (
    <div
      role="progressbar"
      aria-label="Loading"
      className="bg-accent/20 absolute inset-x-0 bottom-0 h-0.5 overflow-hidden"
    >
      <div className="bg-accent animate-route-progress motion-reduce:animate-none motion-reduce:w-full h-full w-1/3" />
    </div>
  );
}
