import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { plantImageQueryOptions } from '../../api/queries';

/**
 * Fetches a plant's photo through the authenticated API client and exposes
 * it as a `blob:` object URL a plain `<img>` can render. A bare
 * `<img src="/api/plants/{id}/image">` cannot work here — the route is
 * bearer-gated with no cookie fallback (TECHNICAL-SPEC.md §12), and browsers
 * never attach a JS-held Authorization header to an image request.
 *
 * The object URL is revoked whenever the underlying blob changes (a
 * replaced photo) or the component unmounts, so it never leaks.
 */
export function usePlantImageUrl(plantId: string, hasImage: boolean): string | null {
  const { data: blob } = useQuery({
    ...plantImageQueryOptions(plantId),
    enabled: hasImage,
  });
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!blob) {
      setUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);

  return url;
}
