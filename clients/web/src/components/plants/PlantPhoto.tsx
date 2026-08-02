import { ImagePlus, Leaf, Trash2 } from 'lucide-react';
import { type ReactElement, useId, useRef } from 'react';

import type { PlantDetailOut } from '../../api/generated';
import { Spinner } from '../feedback/Spinner';
import { useToast } from '../feedback/ToastProvider';
import { secondaryButtonClass } from './styles';
import { useDeletePlantImage, useSetPlantImage } from './usePlantMutations';
import { usePlantImageUrl } from './usePlantImageUrl';

interface PlantPhotoProps {
  plant: PlantDetailOut;
  offline: boolean;
}

// Matches the server's allow-list; the server re-sniffs the bytes regardless,
// this only keeps the file picker tidy.
const ACCEPT = 'image/jpeg,image/png,image/webp,image/gif';

export function PlantPhoto({ plant, offline }: PlantPhotoProps): ReactElement {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const setImage = useSetPlantImage(plant.id);
  const deleteImage = useDeletePlantImage(plant.id);
  const { showToast } = useToast();

  const busy = setImage.isPending || deleteImage.isPending;

  // The photo route is bearer-gated (§12), so the bytes are fetched through
  // the authenticated client and rendered from a blob URL rather than
  // pointing an <img> straight at `plant.image_url`. Invalidation after a
  // replace/delete comes from the same `'plants'`-prefix sweep every other
  // plants mutation already uses, so no manual cache-busting is needed here.
  const src = usePlantImageUrl(plant.id, plant.has_image);

  return (
    <div className="flex items-start gap-4">
      {src ? (
        <img
          src={src}
          alt={plant.name}
          className="bg-surface-sunken h-32 w-32 rounded-md object-cover"
        />
      ) : (
        <div className="bg-surface-sunken flex h-32 w-32 items-center justify-center rounded-md">
          <Leaf className="text-text-muted h-10 w-10" aria-hidden="true" />
        </div>
      )}

      <div className="flex flex-col gap-2">
        <input
          id={inputId}
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="sr-only"
          onChange={(event) => {
            const file = event.target.files?.[0];
            // Reset immediately so picking the *same* file again still fires
            // a change event.
            event.target.value = '';
            if (!file) return;
            setImage.mutate(file, {
              onSuccess: () => showToast('Photo updated', 'success'),
              onError: (problem) => showToast(problem.detail, 'error'),
            });
          }}
        />
        <button
          type="button"
          className={`${secondaryButtonClass} inline-flex items-center gap-1.5`}
          disabled={busy || offline}
          onClick={() => inputRef.current?.click()}
        >
          {setImage.isPending ? <Spinner /> : <ImagePlus className="h-4 w-4" aria-hidden="true" />}
          {plant.has_image ? 'Replace photo' : 'Add photo'}
        </button>

        {plant.has_image ? (
          <button
            type="button"
            className={`${secondaryButtonClass} inline-flex items-center gap-1.5`}
            disabled={busy || offline}
            onClick={() =>
              deleteImage.mutate(undefined, {
                onSuccess: () => showToast('Photo removed', 'success'),
                onError: (problem) => showToast(problem.detail, 'error'),
              })
            }
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            Remove
          </button>
        ) : null}

        <p className="text-text-muted text-xs">JPEG, PNG, WebP or GIF, up to 2 MB.</p>
      </div>
    </div>
  );
}
