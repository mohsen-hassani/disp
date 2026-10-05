import { useQueryClient } from '@tanstack/react-query';
import { Sprout } from 'lucide-react';
import { type ReactElement, useEffect, useState } from 'react';

import { invalidateAffected } from './usePlantMutations';

interface PlantThumbnailProps {
  plantId: string;
  imageUrl: string | null;
  hasImage: boolean;
  name: string;
  className?: string;
}

/**
 * M18-files.md §12: `imageUrl` is a presigned link straight to the bucket (R2
 * in production), not an API route. A cached link can expire, and a photo
 * deleted in the meantime is gone from the bucket, even while the query
 * still holds the old URL. `onError` can't see the HTTP status (an `<img>`
 * tag never exposes it), so an expired link and a missing object are
 * indistinguishable: the fix is the same either way — invalidate the query
 * that owns `imageUrl` so it mints a fresh link on refetch, retry once, then
 * fall back to the placeholder. State (not a `key`-based remount) tracks
 * both, because `imageUrl` itself only changes once the invalidated query
 * actually refetches — the `error` event fires well before that.
 */
export function PlantThumbnail({
  plantId,
  imageUrl,
  hasImage,
  name,
  className,
}: PlantThumbnailProps): ReactElement {
  const queryClient = useQueryClient();
  const [broken, setBroken] = useState(false);
  const [retried, setRetried] = useState(false);
  const baseClass =
    'bg-surface-sunken text-text-muted flex shrink-0 items-center justify-center overflow-hidden rounded-md';

  // A fresh `imageUrl` (the invalidated query refetched with a newly minted
  // link) means the next failure is a new problem, not the one that was
  // just retried — give it its own single retry rather than going straight
  // to the fallback forever.
  useEffect(() => {
    setRetried(false);
    setBroken(false);
  }, [imageUrl]);

  function handleError(): void {
    if (retried) {
      setBroken(true);
      return;
    }
    setRetried(true);
    invalidateAffected(queryClient, plantId);
  }

  if (!hasImage || !imageUrl || broken) {
    return (
      <div className={`${baseClass} ${className ?? 'h-12 w-12'}`}>
        <Sprout className="h-1/2 w-1/2" aria-hidden="true" />
      </div>
    );
  }

  return (
    <div className={`${baseClass} ${className ?? 'h-12 w-12'}`}>
      <img src={imageUrl} alt={name} className="h-full w-full object-cover" onError={handleError} />
    </div>
  );
}
