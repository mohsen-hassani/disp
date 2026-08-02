import * as Dialog from '@radix-ui/react-dialog';
import { type ReactElement, useId, useState } from 'react';

import { useToast } from '../feedback/ToastProvider';
import { SubmitButton } from '../feedback/SubmitButton';
import { useCreatePlant } from './usePlantMutations';
import { inputClass, labelClass, primaryButtonClass, secondaryButtonClass } from './styles';

interface CreatePlantDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (plantId: string) => void;
}

/**
 * Name only is enough to create a plant — description, care notes, the photo
 * and the schedule are all added afterwards on the detail screen. Front-loading
 * them into this dialog would make adding a plant feel like paperwork.
 */
export function CreatePlantDialog({
  open,
  onOpenChange,
  onCreated,
}: CreatePlantDialogProps): ReactElement {
  const nameId = useId();
  const titleId = useId();
  const [name, setName] = useState('');
  const createPlant = useCreatePlant();
  const { showToast } = useToast();

  function close(): void {
    setName('');
    createPlant.reset();
    onOpenChange(false);
  }

  return (
    <Dialog.Root open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content
          aria-labelledby={titleId}
          className="bg-surface border-border fixed top-1/2 left-1/2 w-[min(28rem,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-md border p-5 shadow-lg"
        >
          <Dialog.Title id={titleId} className="text-text mb-4 text-base font-medium">
            New plant
          </Dialog.Title>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              const trimmed = name.trim();
              if (!trimmed) return;
              createPlant.mutate(
                { name: trimmed },
                {
                  onSuccess: (plant) => {
                    showToast(`${plant.name} added`, 'success');
                    close();
                    onCreated(plant.id);
                  },
                  onError: (problem) => showToast(problem.detail, 'error'),
                },
              );
            }}
          >
            <label htmlFor={nameId} className={labelClass}>
              Name
            </label>
            <input
              id={nameId}
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={120}
              required
              // No autoFocus: Radix's Dialog moves focus to the first
              // focusable element in the content on open already.
              placeholder="Sansevieria"
              className={inputClass}
            />
            <p className="text-text-muted mt-2 text-xs">
              You can add a photo, care notes and watering intervals next.
            </p>

            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={close} className={secondaryButtonClass}>
                Cancel
              </button>
              <SubmitButton
                submitting={createPlant.isPending}
                disabled={!name.trim()}
                className={primaryButtonClass}
              >
                Create plant
              </SubmitButton>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
