import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { ReactElement } from 'react';

interface ShortcutsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// §16.5's table, verbatim.
const SHORTCUTS: ReadonlyArray<{ keys: string; action: string }> = [
  { keys: 'g then d', action: 'Go to dashboard' },
  { keys: 'g then n', action: 'Go to notes' },
  { keys: 'n', action: 'New note dialog' },
  { keys: '/', action: 'Focus search (on /notes)' },
  { keys: '?', action: 'Show this dialog' },
  { keys: 'Escape', action: 'Close topmost overlay' },
];

export function ShortcutsDialog({ open, onOpenChange }: ShortcutsDialogProps): ReactElement {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content
          aria-labelledby="shortcuts-dialog-title"
          className="border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4"
        >
          <div className="mb-3 flex items-center justify-between">
            <Dialog.Title id="shortcuts-dialog-title" className="text-text text-sm font-medium">
              Keyboard shortcuts
            </Dialog.Title>
            <Dialog.Close
              aria-label="Close"
              className="text-text-muted focus-visible:outline-accent rounded-sm p-1 focus-visible:outline focus-visible:outline-2"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </Dialog.Close>
          </div>
          <dl className="flex flex-col gap-2 text-sm">
            {SHORTCUTS.map((shortcut) => (
              <div key={shortcut.keys} className="flex items-center justify-between gap-4">
                <dt>
                  <kbd className="border-border bg-surface-sunken rounded-sm border px-1.5 py-0.5 font-mono text-xs">
                    {shortcut.keys}
                  </kbd>
                </dt>
                <dd className="text-text-muted">{shortcut.action}</dd>
              </div>
            ))}
          </dl>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
