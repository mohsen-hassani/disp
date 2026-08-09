import { Link } from '@tanstack/react-router';
import type { ReactElement } from 'react';

import type { PlantOut } from '../../api/generated';
import { PlantDueBadge } from './DueBadge';
import { PlantThumbnail } from './PlantThumbnail';

interface PlantCardProps {
  plant: PlantOut;
}

/** M14 §5's list row: thumbnail, name, due badge (from the rollups the list response already carries), next-due date. */
export function PlantCard({ plant }: PlantCardProps): ReactElement {
  return (
    <Link
      to="/plants/$plantId"
      params={{ plantId: plant.id }}
      className="border-border bg-surface focus-visible:outline-accent flex items-center gap-3 rounded-md border p-3 focus-visible:outline focus-visible:outline-2"
    >
      <PlantThumbnail imageUrl={plant.image_url} hasImage={plant.has_image} name={plant.name} />
      <div className="min-w-0 flex-1">
        <p className="text-text truncate text-sm font-medium">{plant.name}</p>
        <div className="mt-1">
          <PlantDueBadge
            dueCount={plant.due_count}
            maxDaysOverdue={plant.max_days_overdue}
            nextDueOn={plant.next_due_on}
          />
        </div>
      </div>
    </Link>
  );
}
