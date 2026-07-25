import type { ReactElement } from 'react';

interface TileSkeletonProps {
  title: string;
}

// §13.8 / §21 A14: no shimmer, just static muted bars — `aria-hidden`, with
// an accompanying visually hidden "Loading…" for the a11y tree.
export function TileSkeleton({ title }: TileSkeletonProps): ReactElement {
  return (
    <div
      aria-busy="true"
      className="border-border bg-surface flex flex-col gap-2 rounded-md border p-4"
    >
      <span className="sr-only">Loading {title}…</span>
      <div aria-hidden="true" className="flex flex-col gap-2">
        <div className="bg-surface-sunken h-4 w-1/3 rounded-sm" />
        <div className="bg-surface-sunken h-3 w-full rounded-sm" />
        <div className="bg-surface-sunken h-3 w-5/6 rounded-sm" />
      </div>
    </div>
  );
}
