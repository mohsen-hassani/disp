import * as Dialog from '@radix-ui/react-dialog';
import { lazy, type ReactElement, Suspense, useId, useState } from 'react';

import type { TileAction } from '../../api/generated';
import { useOfflineState } from '../../hooks/useOfflineState';
import { useToast } from '../feedback/ToastProvider';
import { describeActionError, type TileActionError, useTileAction } from './useTileAction';

// Lazy: pulls in SchemaForm + all 8 widget files (~1KB gzipped of import
// glue here, but the whole schema-form module behind it), and this button
// sits on the dashboard's most-loaded path (TileGrid -> TileCard). A plain
// top-level import would ship that weight in the dashboard's own chunk
// whether or not the user ever opens a dialog with a body_schema.
const TileActionDialog = lazy(() =>
  import('./TileActionDialog').then((m) => ({ default: m.TileActionDialog })),
);

interface TileActionButtonProps {
  action: TileAction;
  tileKey: string;
}

const buttonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

// §13.6: no `body_schema` fires immediately, except `DELETE`, which
// confirms first. With `body_schema`, delegates entirely to
// `TileActionDialog` — this component just owns the trigger + the
// confirmation step, not the request itself in that case.
export function TileActionButton({ action, tileKey }: TileActionButtonProps): ReactElement {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const confirmTitleId = useId();
  const { showToast } = useToast();
  const mutation = useTileAction(tileKey);
  const isOffline = useOfflineState();

  if (action.body_schema) {
    return (
      <>
        <button
          type="button"
          onClick={() => setDialogOpen(true)}
          disabled={isOffline}
          title={isOffline ? "You're offline." : undefined}
          className={buttonClass}
        >
          {action.label}
        </button>
        {dialogOpen && (
          <Suspense fallback={null}>
            <TileActionDialog
              action={action}
              tileKey={tileKey}
              open={dialogOpen}
              onOpenChange={setDialogOpen}
            />
          </Suspense>
        )}
      </>
    );
  }

  const fire = (): void => {
    mutation.mutate(
      { method: action.method, path: action.path },
      { onError: (error) => showToast(describeActionError(error as TileActionError), 'error') },
    );
  };

  if (action.method === 'DELETE') {
    return (
      <>
        <button
          type="button"
          onClick={() => setConfirmOpen(true)}
          disabled={mutation.isPending || isOffline}
          title={isOffline ? "You're offline." : undefined}
          className={buttonClass}
        >
          {action.label}
        </button>
        <Dialog.Root open={confirmOpen} onOpenChange={setConfirmOpen}>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 bg-black/40" />
            <Dialog.Content
              aria-labelledby={confirmTitleId}
              className="border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4"
            >
              <Dialog.Title id={confirmTitleId} className="text-text mb-2 text-sm font-medium">
                {action.label}?
              </Dialog.Title>
              <p className="text-text-muted mb-4 text-sm">This can&apos;t be undone.</p>
              <div className="flex justify-end gap-2">
                <Dialog.Close className="border-border text-text rounded-sm border px-3 py-1.5 text-sm">
                  Cancel
                </Dialog.Close>
                <button
                  type="button"
                  onClick={() => {
                    setConfirmOpen(false);
                    fire();
                  }}
                  className="bg-danger text-accent-text rounded-sm px-3 py-1.5 text-sm font-medium"
                >
                  {action.label}
                </button>
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </>
    );
  }

  return (
    <button
      type="button"
      onClick={fire}
      disabled={mutation.isPending || isOffline}
      title={isOffline ? "You're offline." : undefined}
      className={buttonClass}
    >
      {action.label}
    </button>
  );
}
