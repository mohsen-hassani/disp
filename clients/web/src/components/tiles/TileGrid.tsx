import type { ReactElement } from 'react';

import type { TileData, TileSpec } from '../../api/generated';
import { TileCard } from './TileCard';
import { TileSkeleton } from './TileSkeleton';

interface TileGridProps {
  specs: TileSpec[];
  /** `undefined` while the bulk `/tiles` fetch is still in flight — renders skeletons for every spec. */
  tilesByKey?: Record<string, TileData>;
}

// §21 A15: a `<ul>` of `<li>`; each tile is an `<article>` (TileCard's own
// job). §13.2's grid: 1/2/3 columns at base/md/lg (xl repeats lg), `large`
// spans 2 columns from md up. Only `large` gets a span override — an
// unknown `size` value therefore falls back to the same 1-column
// treatment as `medium`, satisfying that requirement without a separate
// branch for it.
export function TileGrid({ specs, tilesByKey }: TileGridProps): ReactElement {
  return (
    <ul className="grid auto-rows-min grid-cols-1 items-start gap-4 md:grid-cols-2 lg:grid-cols-3">
      {specs.map((spec) => (
        <li key={spec.key} className={spec.size === 'large' ? 'md:col-span-2' : undefined}>
          {tilesByKey ? (
            <TileCard spec={spec} initialData={tilesByKey[spec.key]} />
          ) : (
            <TileSkeleton title={spec.title} />
          )}
        </li>
      ))}
    </ul>
  );
}
