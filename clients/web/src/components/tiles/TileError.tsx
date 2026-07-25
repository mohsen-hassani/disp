import type { ReactElement } from 'react';
import { useId } from 'react';

interface TileErrorProps {
  title: string;
  onRetry: () => void;
}

// §13.8: the *request* failed (network, 5xx) — distinct from a provider
// that failed server-side, which already arrives as valid `TileData` with
// an `empty_text` and is rendered as a normal tile, never here.
export function TileError({ title, onRetry }: TileErrorProps): ReactElement {
  const headingId = useId();
  return (
    <article
      aria-labelledby={headingId}
      className="border-border bg-surface flex flex-col gap-2 rounded-md border p-4"
    >
      <h3 id={headingId} className="text-text text-sm font-medium">
        {title}
      </h3>
      <p className="text-danger text-sm">This tile couldn&apos;t be loaded.</p>
      <button
        type="button"
        onClick={onRetry}
        className="border-border text-text focus-visible:outline-accent self-start rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        Retry
      </button>
    </article>
  );
}
