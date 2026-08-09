import { Sprout } from 'lucide-react';
import { type ReactElement, useState } from 'react';

interface PlantThumbnailProps {
  imageUrl: string | null;
  hasImage: boolean;
  name: string;
  className?: string;
}

/**
 * M14 §5: "Plant photos are files on a volume, not rows" — a database-only
 * restore leaves `has_image: true` with the file gone, so `<img src>`
 * 404s. That must render as a placeholder, never a broken image icon. State
 * (not a `key`-based remount) tracks the failure, because `imageUrl` itself
 * doesn't change when the request fails — only the `error` event does.
 */
export function PlantThumbnail({
  imageUrl,
  hasImage,
  name,
  className,
}: PlantThumbnailProps): ReactElement {
  const [broken, setBroken] = useState(false);
  const baseClass =
    'bg-surface-sunken text-text-muted flex shrink-0 items-center justify-center overflow-hidden rounded-md';

  if (!hasImage || !imageUrl || broken) {
    return (
      <div className={`${baseClass} ${className ?? 'h-12 w-12'}`}>
        <Sprout className="h-1/2 w-1/2" aria-hidden="true" />
      </div>
    );
  }

  return (
    <div className={`${baseClass} ${className ?? 'h-12 w-12'}`}>
      <img
        src={imageUrl}
        alt={name}
        className="h-full w-full object-cover"
        onError={() => setBroken(true)}
      />
    </div>
  );
}
