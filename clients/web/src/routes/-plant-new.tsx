import { useNavigate } from '@tanstack/react-router';
import { type ReactElement, useState } from 'react';

import type { ProblemDetail } from '../api/problem';
import { PlantEditor } from '../components/plants/PlantEditor';
import { describePlantError, useCreatePlant } from '../components/plants/usePlantMutations';
import type { ServerFieldError } from '../lib/mapValidationErrors';

// Router-ignored (leading `-`) — see `-login.tsx`'s doc for why.
export function PlantNewPage(): ReactElement {
  const navigate = useNavigate();
  const createMutation = useCreatePlant();
  const [error, setError] = useState<string | undefined>();
  const [serverErrors, setServerErrors] = useState<ServerFieldError[] | undefined>();

  return (
    <>
      <h1>New plant</h1>
      <PlantEditor
        mode="create"
        submitting={createMutation.isPending}
        error={error}
        serverErrors={serverErrors}
        onSubmit={(values) => {
          setError(undefined);
          setServerErrors(undefined);
          createMutation.mutate(
            {
              name: values.name,
              description: values.description,
              care_notes: values.care_notes,
            },
            {
              // M14 §5: intervals aren't part of this form — land on the
              // detail screen, where they're added next.
              onSuccess: (plant) =>
                void navigate({ to: '/plants/$plantId', params: { plantId: plant.id } }),
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
        onCancel={() => void navigate({ to: '/plants' })}
      />
    </>
  );
}
