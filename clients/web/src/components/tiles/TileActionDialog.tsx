import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { type ReactElement, useId, useState } from 'react';

import type { TileAction } from '../../api/generated';
import { SchemaForm, type ServerFieldError } from '../schema-form/SchemaForm';
import type { JsonSchemaDoc } from '../schema-form/types';
import { describeActionError, type TileActionError, useTileAction } from './useTileAction';

interface TileActionDialogProps {
  action: TileAction;
  tileKey: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// §13.6: an action with `body_schema` opens this, containing a `SchemaForm`
// generated from that schema. A failing submit keeps the dialog open with
// the error inline (below) so input isn't lost — success closes it.
export function TileActionDialog({
  action,
  tileKey,
  open,
  onOpenChange,
}: TileActionDialogProps): ReactElement {
  const titleId = useId();
  const [error, setError] = useState<string | undefined>();
  const [serverErrors, setServerErrors] = useState<ServerFieldError[] | undefined>();
  const mutation = useTileAction(tileKey);

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (next) {
          setError(undefined);
          setServerErrors(undefined);
        }
        onOpenChange(next);
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content
          aria-labelledby={titleId}
          className="border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4"
        >
          <div className="mb-3 flex items-center justify-between">
            <Dialog.Title id={titleId} className="text-text text-sm font-medium">
              {action.label}
            </Dialog.Title>
            <Dialog.Close
              aria-label="Close"
              className="text-text-muted focus-visible:outline-accent flex h-11 w-11 items-center justify-center rounded-sm focus-visible:outline focus-visible:outline-2"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </Dialog.Close>
          </div>
          <SchemaForm
            schema={(action.body_schema ?? {}) as JsonSchemaDoc}
            initialValue={{}}
            error={error}
            serverErrors={serverErrors}
            submitLabel={action.label}
            onSubmit={async (values) => {
              setError(undefined);
              setServerErrors(undefined);
              try {
                await mutation.mutateAsync({
                  method: action.method,
                  path: action.path,
                  body: values,
                });
                onOpenChange(false);
              } catch (thrown) {
                const actionError = thrown as TileActionError;
                if (actionError.problem.status === 422 && actionError.problem.errors) {
                  setServerErrors(actionError.problem.errors);
                } else {
                  setError(describeActionError(actionError));
                }
              }
            }}
          />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
