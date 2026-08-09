import { useQuery } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { type ReactElement, useEffect, useState } from 'react';

import type { ProblemDetail } from '../api/problem';
import { plantDetailQueryOptions } from '../api/queries';
import { PlantEditor } from '../components/plants/PlantEditor';
import { describePlantError, useUpdatePlant } from '../components/plants/usePlantMutations';
import { setPageTitleOverride } from '../hooks/usePageTitle';
import type { ServerFieldError } from '../lib/mapValidationErrors';

interface PlantEditPageProps {
  plantId: string;
}

// Router-ignored (leading `-`) — see `-login.tsx`'s doc for why. The
// route's own `loader` already warmed this exact query key, so this
// `useQuery` call is a cache read, not a second network round trip.
export function PlantEditPage({ plantId }: PlantEditPageProps): ReactElement {
  const navigate = useNavigate();
  const plantQuery = useQuery(plantDetailQueryOptions(plantId));
  const updateMutation = useUpdatePlant(plantId);
  const [error, setError] = useState<string | undefined>();
  const [serverErrors, setServerErrors] = useState<ServerFieldError[] | undefined>();
  const plant = plantQuery.data;

  useEffect(() => {
    if (!plant) {
      return undefined;
    }
    setPageTitleOverride(`Edit ${plant.name} · DISP`);
    return () => setPageTitleOverride(null);
  }, [plant]);

  if (plantQuery.isPending) {
    return <p aria-busy="true">Loading…</p>;
  }
  if (plantQuery.isError || !plant) {
    return <p role="alert">Failed to load the plant.</p>;
  }

  return (
    <>
      <h1>Edit {plant.name}</h1>
      <PlantEditor
        mode="edit"
        initialName={plant.name}
        initialDescription={plant.description ?? ''}
        initialCareNotes={plant.care_notes ?? ''}
        submitting={updateMutation.isPending}
        error={error}
        serverErrors={serverErrors}
        onSubmit={(values) => {
          setError(undefined);
          setServerErrors(undefined);
          updateMutation.mutate(
            {
              name: values.name,
              description: values.description,
              care_notes: values.care_notes,
            },
            {
              onSuccess: () => void navigate({ to: '/plants/$plantId', params: { plantId } }),
              onError: (thrownError: ProblemDetail) => {
                if (thrownError.status === 422 && thrownError.errors) {
                  setServerErrors(thrownError.errors);
                } else {
                  setError(describePlantError(thrownError));
                }
              },
            },
          );
        }}
        onCancel={() => void navigate({ to: '/plants/$plantId', params: { plantId } })}
      />
    </>
  );
}
