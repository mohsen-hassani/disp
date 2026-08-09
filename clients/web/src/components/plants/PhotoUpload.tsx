import { type ChangeEvent, type ReactElement, useRef, useState } from 'react';

import type { PlantDetailOut } from '../../api/generated';
import { useOfflineState } from '../../hooks/useOfflineState';
import { useToast } from '../feedback/ToastProvider';
import { PlantThumbnail } from './PlantThumbnail';
import { describePlantError, useDeletePlantImage, useSetPlantImage } from './usePlantMutations';

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
// `DISP_PLANTS_MAX_IMAGE_BYTES`'s shipped default (M14 §5) — a fast
// client-side check only. The server enforces its own (possibly
// operator-overridden) limit and is always the source of truth; a rejection
// there still surfaces via `describePlantError`.
const MAX_IMAGE_BYTES = 2 * 1024 * 1024;

interface PhotoUploadProps {
  plant: PlantDetailOut;
}

const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

export function PhotoUpload({ plant }: PhotoUploadProps): ReactElement {
  const isOffline = useOfflineState();
  const { showToast } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [clientError, setClientError] = useState<string | undefined>();
  const setImage = useSetPlantImage();
  const deleteImage = useDeletePlantImage();

  function handleFileChange(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) {
      return;
    }
    setClientError(undefined);
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setClientError('Choose a JPEG, PNG, WebP or GIF image.');
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setClientError(`Image is too large — the limit is ${MAX_IMAGE_BYTES / (1024 * 1024)} MB.`);
      return;
    }
    setImage.mutate(
      { plantId: plant.id, file },
      { onError: (error) => showToast(describePlantError(error), 'error') },
    );
  }

  return (
    <div className="flex items-center gap-3">
      <PlantThumbnail
        imageUrl={plant.image_url}
        hasImage={plant.has_image}
        name={plant.name}
        className="h-20 w-20"
      />
      <div className="flex flex-col items-start gap-1">
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(',')}
          className="hidden"
          onChange={handleFileChange}
        />
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={isOffline || setImage.isPending}
          title={isOffline ? "You're offline." : undefined}
          className={secondaryButtonClass}
        >
          {setImage.isPending ? 'Uploading…' : plant.has_image ? 'Replace photo' : 'Add photo'}
        </button>
        {plant.has_image && (
          <button
            type="button"
            onClick={() =>
              deleteImage.mutate(plant.id, {
                onError: (error) => showToast(describePlantError(error), 'error'),
              })
            }
            disabled={isOffline || deleteImage.isPending}
            title={isOffline ? "You're offline." : undefined}
            className="text-danger text-xs disabled:opacity-60"
          >
            Remove photo
          </button>
        )}
        {clientError && (
          <p role="alert" className="text-danger text-xs">
            {clientError}
          </p>
        )}
      </div>
    </div>
  );
}
