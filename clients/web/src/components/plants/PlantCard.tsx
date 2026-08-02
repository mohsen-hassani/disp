import { Link } from '@tanstack/react-router';
import { Leaf } from 'lucide-react';
import type { ReactElement } from 'react';

import type { PlantOut } from '../../api/generated';
import { TONE_CLASS, describeNextDue, dueTone } from './dueText';
import { usePlantImageUrl } from './usePlantImageUrl';

interface PlantCardProps {
  plant: PlantOut;
}

/** One row in the plants list: photo, name, and what it currently owes you. */
export function PlantCard({ plant }: PlantCardProps): ReactElement {
  const overdue = plant.due_count > 0;
  const tone = overdue ? dueTone(plant.max_days_overdue) : 'upcoming';
  // Bearer-gated route (§12) — fetched via the authenticated client and
  // rendered from a blob URL, same reasoning as PlantPhoto.
  const src = usePlantImageUrl(plant.id, plant.has_image);

  return (
    <Link
      to="/plants/$plantId"
      params={{ plantId: plant.id }}
      className="border-border bg-surface hover:bg-surface-sunken focus-visible:outline-accent flex items-center gap-4 rounded-md border p-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
    >
      {src ? (
        <img
          src={src}
          alt=""
          loading="lazy"
          className="bg-surface-sunken h-14 w-14 shrink-0 rounded-md object-cover"
        />
      ) : (
        <div className="bg-surface-sunken flex h-14 w-14 shrink-0 items-center justify-center rounded-md">
          <Leaf className="text-text-muted h-6 w-6" aria-hidden="true" />
        </div>
      )}

      <div className="min-w-0 flex-1">
        <p className="text-text truncate text-sm font-medium">{plant.name}</p>
        {plant.description ? (
          <p className="text-text-muted truncate text-sm">{plant.description}</p>
        ) : null}
      </div>

      {overdue ? (
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${TONE_CLASS[tone]}`}>
          {plant.due_count} due
          {plant.max_days_overdue > 0 ? ` · ${plant.max_days_overdue}d behind` : ''}
        </span>
      ) : plant.next_due_on ? (
        <span className="text-text-muted shrink-0 text-xs">
          {describeNextDue(plant.next_due_on)}
        </span>
      ) : (
        <span className="text-text-muted shrink-0 text-xs">No schedule</span>
      )}
    </Link>
  );
}
