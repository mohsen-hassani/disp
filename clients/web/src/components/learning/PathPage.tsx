import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { CheckCircle2, ListChecks, Trash2 } from 'lucide-react';
import { type FormEvent, type ReactElement, useState } from 'react';

import type { PathItemOut } from '../../api/generated';
import { learningPathQueryOptions } from '../../api/queries';
import { EmptyState } from '../feedback/EmptyState';
import { useToast } from '../feedback/ToastProvider';
import {
  describeLearningError,
  useApprovePath,
  useDeletePathItem,
  useUpdatePathItem,
} from './useLearningMutations';

const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

const TIER_LABEL: Record<string, string> = {
  concepts: 'Concepts',
  beginner: 'Beginner',
  intermediate: 'Intermediate',
  advanced: 'Advanced',
};

const TIER_ORDER = ['concepts', 'beginner', 'intermediate', 'advanced'];

interface PathPageProps {
  courseId: string;
}

function PathItemRow({ item, courseId }: { item: PathItemOut; courseId: string }): ReactElement {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(item.title);
  const { showToast } = useToast();
  const updateItem = useUpdatePathItem();
  const deleteItem = useDeletePathItem();

  function handleSave(event: FormEvent): void {
    event.preventDefault();
    updateItem.mutate(
      { pathItemId: item.id, courseId, payload: { title } },
      {
        onSuccess: () => setEditing(false),
        onError: (error) => showToast(describeLearningError(error), 'error'),
      },
    );
  }

  return (
    <li className="border-border bg-surface flex items-center justify-between gap-3 rounded-md border p-3 text-sm">
      {editing ? (
        <form onSubmit={handleSave} className="flex min-w-0 flex-1 items-center gap-2">
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className="border-border bg-surface min-w-0 flex-1 rounded-sm border px-2 py-1 text-sm"
          />
          <button type="submit" disabled={updateItem.isPending} className={secondaryButtonClass}>
            Save
          </button>
          <button type="button" onClick={() => setEditing(false)} className={secondaryButtonClass}>
            Cancel
          </button>
        </form>
      ) : (
        <>
          {item.status === 'approved' ? (
            <Link
              to="/learning/$courseId/items/$itemId"
              params={{ courseId, itemId: item.id }}
              className="min-w-0 flex-1 truncate font-medium"
            >
              {item.title}
            </Link>
          ) : (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="min-w-0 flex-1 truncate text-left font-medium"
            >
              {item.title}
            </button>
          )}
          <span className="text-text-muted shrink-0 text-xs">{item.est_minutes} min</span>
          {item.completion_status === 'completed' && (
            <CheckCircle2 className="text-success h-4 w-4 shrink-0" aria-hidden="true" />
          )}
          {item.status === 'draft' && (
            <button
              type="button"
              aria-label={`Delete ${item.title}`}
              onClick={() =>
                deleteItem.mutate(
                  { pathItemId: item.id, courseId },
                  { onError: (error) => showToast(describeLearningError(error), 'error') },
                )
              }
              disabled={deleteItem.isPending}
              className="text-danger shrink-0"
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </>
      )}
    </li>
  );
}

/** M20 §23: `/learning/$courseId/path` — the draft path a curator edits, or the approved path a learner works through. */
export function PathPage({ courseId }: PathPageProps): ReactElement {
  const pathQuery = useQuery(learningPathQueryOptions(courseId));
  const { showToast } = useToast();
  const approvePath = useApprovePath();

  if (pathQuery.isPending) {
    return <p aria-busy="true">Loading…</p>;
  }
  if (pathQuery.isError) {
    return <p role="alert">Failed to load the learning path.</p>;
  }

  const items = pathQuery.data ?? [];
  const isDraft = items.some((item) => item.status === 'draft');

  if (items.length === 0) {
    return (
      <EmptyState
        icon={ListChecks}
        title="No path yet. Generate one from the course detail page after indexing."
      />
    );
  }

  const byTier = new Map<string, PathItemOut[]>();
  for (const item of [...items].sort((a, b) => a.order_index - b.order_index)) {
    const bucket = byTier.get(item.tier) ?? [];
    bucket.push(item);
    byTier.set(item.tier, bucket);
  }

  function handleApprove(): void {
    approvePath.mutate(courseId, {
      onSuccess: () => showToast('Path approved.', 'success'),
      onError: (error) => showToast(describeLearningError(error), 'error'),
    });
  }

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <h1>Learning path</h1>
        {isDraft && (
          <button
            type="button"
            onClick={handleApprove}
            disabled={approvePath.isPending}
            className={primaryButtonClass}
          >
            Approve path
          </button>
        )}
      </div>

      {TIER_ORDER.filter((tier) => byTier.has(tier)).map((tier) => (
        <div key={tier} className="mb-6">
          <h2 className="text-text-muted mb-2 text-xs font-medium tracking-wide uppercase">
            {TIER_LABEL[tier] ?? tier}
          </h2>
          <ul className="flex flex-col gap-2">
            {(byTier.get(tier) ?? []).map((item) => (
              <PathItemRow key={item.id} item={item} courseId={courseId} />
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}
