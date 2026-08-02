import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from '@tanstack/react-router';
import { ArrowLeft } from 'lucide-react';
import { type ReactElement, useEffect, useId, useState } from 'react';

import { plantDetailQueryOptions, plantHistoryQueryOptions } from '../api/queries';
import { SubmitButton } from '../components/feedback/SubmitButton';
import { useToast } from '../components/feedback/ToastProvider';
import { AddIntervalForm } from '../components/plants/AddIntervalForm';
import { CareIntervalList } from '../components/plants/CareIntervalList';
import { PlantPhoto } from '../components/plants/PlantPhoto';
import {
  dangerButtonClass,
  inputClass,
  labelClass,
  primaryButtonClass,
  secondaryButtonClass,
} from '../components/plants/styles';
import { useDeletePlant, useUpdatePlant } from '../components/plants/usePlantMutations';
import { useOnlineStatus } from '../hooks/useOnlineStatus';
import { setPageTitleOverride } from '../hooks/usePageTitle';

interface PlantDetailPageProps {
  plantId: string;
}

export function PlantDetailPage({ plantId }: PlantDetailPageProps): ReactElement {
  const online = useOnlineStatus();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const { data: plant } = useQuery(plantDetailQueryOptions(plantId));
  const historyQuery = useQuery(plantHistoryQueryOptions(plantId));
  const deletePlant = useDeletePlant();
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useEffect(() => {
    if (plant) setPageTitleOverride(`${plant.name} · DISP`);
    return () => setPageTitleOverride(null);
  }, [plant?.name]);

  // The route loader has already resolved this query, so `plant` is only
  // undefined during a background refetch of an evicted cache entry.
  if (!plant) return <p className="text-text-muted text-sm">Loading…</p>;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <Link
          to="/plants"
          className="text-text-muted hover:text-text mb-3 inline-flex items-center gap-1.5 text-sm"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          All plants
        </Link>
        <h1 className="text-text text-xl font-semibold">{plant.name}</h1>
      </div>

      <PlantPhoto plant={plant} offline={!online} />

      <PlantDetailsForm plantId={plantId} plant={plant} offline={!online} />

      <section className="flex flex-col gap-3">
        <h2 className="text-text text-base font-medium">Care schedule</h2>
        <CareIntervalList plantId={plantId} intervals={plant.intervals} offline={!online} />
        <AddIntervalForm plantId={plantId} offline={!online} />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-text text-base font-medium">Recent care</h2>
        {historyQuery.data && historyQuery.data.length > 0 ? (
          <ul className="flex flex-col gap-1">
            {historyQuery.data.map((log) => (
              <li key={log.id} className="text-text-muted flex justify-between gap-4 text-sm">
                <span className="text-text">{log.action_name}</span>
                <span>
                  {log.completed_on}
                  {log.days_late > 0 ? ` · ${log.days_late}d late` : ''}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-text-muted text-sm">Nothing logged yet.</p>
        )}
      </section>

      <section className="flex flex-col items-start gap-2">
        <h2 className="text-text text-base font-medium">Danger zone</h2>
        {confirmingDelete ? (
          <div className="flex items-center gap-2">
            <span className="text-text-muted text-sm">
              Delete {plant.name} and its whole schedule?
            </span>
            <button
              type="button"
              className={dangerButtonClass}
              disabled={deletePlant.isPending}
              onClick={() =>
                deletePlant.mutate(plantId, {
                  onSuccess: () => {
                    showToast(`${plant.name} deleted`, 'success');
                    void navigate({ to: '/plants' });
                  },
                  onError: (problem) => showToast(problem.detail, 'error'),
                })
              }
            >
              Delete
            </button>
            <button
              type="button"
              className={secondaryButtonClass}
              onClick={() => setConfirmingDelete(false)}
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            className={dangerButtonClass}
            disabled={!online}
            onClick={() => setConfirmingDelete(true)}
          >
            Delete plant
          </button>
        )}
      </section>
    </div>
  );
}

function PlantDetailsForm({
  plantId,
  plant,
  offline,
}: {
  plantId: string;
  plant: { name: string; description: string | null; care_notes: string | null };
  offline: boolean;
}): ReactElement {
  const nameId = useId();
  const descriptionId = useId();
  const notesId = useId();
  const { showToast } = useToast();
  const updatePlant = useUpdatePlant(plantId);

  const [name, setName] = useState(plant.name);
  const [description, setDescription] = useState(plant.description ?? '');
  const [careNotes, setCareNotes] = useState(plant.care_notes ?? '');

  // Re-seed when the server's copy changes underneath (another tab, a refetch).
  useEffect(() => {
    setName(plant.name);
    setDescription(plant.description ?? '');
    setCareNotes(plant.care_notes ?? '');
  }, [plant.name, plant.description, plant.care_notes]);

  const dirty =
    name !== plant.name ||
    description !== (plant.description ?? '') ||
    careNotes !== (plant.care_notes ?? '');

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        updatePlant.mutate(
          {
            name: name.trim(),
            description: description.trim() || null,
            care_notes: careNotes.trim() || null,
          },
          {
            onSuccess: () => showToast('Saved', 'success'),
            onError: (problem) => showToast(problem.detail, 'error'),
          },
        );
      }}
    >
      <div>
        <label htmlFor={nameId} className={labelClass}>
          Name
        </label>
        <input
          id={nameId}
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={120}
          required
          className={inputClass}
        />
      </div>

      <div>
        <label htmlFor={descriptionId} className={labelClass}>
          Description
        </label>
        <input
          id={descriptionId}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={2000}
          placeholder="Where it lives, where it came from…"
          className={inputClass}
        />
      </div>

      <div>
        <label htmlFor={notesId} className={labelClass}>
          Care notes
        </label>
        <textarea
          id={notesId}
          value={careNotes}
          onChange={(event) => setCareNotes(event.target.value)}
          maxLength={20000}
          rows={5}
          placeholder="Bright indirect light. Let the soil dry out fully between waterings."
          className={inputClass}
        />
        <p className="text-text-muted mt-1 text-xs">
          Free text — the general rules for looking after this plant. Recurring actions go in the
          care schedule below.
        </p>
      </div>

      <SubmitButton
        submitting={updatePlant.isPending}
        disabled={!dirty || offline || !name.trim()}
        className={`${primaryButtonClass} self-start`}
      >
        Save changes
      </SubmitButton>
    </form>
  );
}
