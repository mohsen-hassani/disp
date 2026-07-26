import { X } from 'lucide-react';
import type { ReactElement } from 'react';

import { useInstallPrompt } from '../hooks/useInstallPrompt';

const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-3 py-1.5 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2';
const iconButtonClass =
  'text-text-muted focus-visible:outline-accent flex h-11 w-11 shrink-0 items-center justify-center rounded-sm focus-visible:outline focus-visible:outline-2';

/**
 * §17.3: never a modal, never blocks content — a dismissible inline card,
 * placement owned by M05's dashboard (`routes/_app.index.tsx`), logic owned
 * here. Renders nothing once dismissed, already standalone, or on a browser
 * that gives neither a native prompt nor is iOS Safari.
 */
export function InstallPromptCard(): ReactElement | null {
  const { variant, promptInstall, dismiss } = useInstallPrompt();

  if (!variant) {
    return null;
  }

  return (
    <div className="border-border bg-surface mb-4 flex items-center justify-between gap-3 rounded-md border p-3 text-sm">
      <p className="text-text-muted">
        {variant === 'android'
          ? 'Install DISP for quick access from your home screen.'
          : 'Install DISP: tap Share, then "Add to Home Screen".'}
      </p>
      <div className="flex shrink-0 items-center gap-2">
        {variant === 'android' && (
          <button type="button" onClick={promptInstall} className={primaryButtonClass}>
            Install
          </button>
        )}
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss install prompt"
          className={iconButtonClass}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
