import { type QueryKey, useMutation, useQueryClient } from '@tanstack/react-query';

import type {
  CareIntervalCreate,
  CareIntervalOut,
  CareIntervalUpdate,
  CompleteRequest,
  CompleteResult,
  PlantCreate,
  PlantDetailOut,
  PlantOut,
  PlantUpdate,
} from '../../api/generated';
import {
  plantsAddInterval,
  plantsCompleteInterval,
  plantsCreate,
  plantsDelete,
  plantsDeleteImage,
  plantsDeleteInterval,
  plantsSetImage,
  plantsUpdate,
  plantsUpdateInterval,
} from '../../api/generated';
import { type ProblemDetail, parseProblem } from '../../api/problem';
import { qk } from '../../api/queryKeys';

// Every plants query key starts with 'plants', so one prefix invalidation
// covers the list, the detail, the history, the due summary and every cached
// calendar month. Marking one action done legitimately changes all of them
// (the next occurrence moves), so there is nothing finer worth targeting.
const PLANTS_PREFIX: QueryKey = qk.plants.all();
const PLANTS_TILE_KEY = qk.dashboard.tile('plants.due');

function invalidatePlants(queryClient: ReturnType<typeof useQueryClient>): void {
  void queryClient.invalidateQueries({ queryKey: PLANTS_PREFIX });
  void queryClient.invalidateQueries({ queryKey: PLANTS_TILE_KEY });
}

async function throwProblem(response: Response | undefined, error: unknown): Promise<never> {
  throw parseProblem(response ?? new Response(null, { status: 0 }), error);
}

export function useCreatePlant() {
  const queryClient = useQueryClient();
  return useMutation<PlantOut, ProblemDetail, PlantCreate>({
    mutationFn: async (payload) => {
      const { data, error, response } = await plantsCreate({ body: payload });
      if (!response?.ok || !data) {
        return throwProblem(response, error);
      }
      return data;
    },
    onSuccess: () => invalidatePlants(queryClient),
  });
}

export function useUpdatePlant(plantId: string) {
  const queryClient = useQueryClient();
  return useMutation<PlantOut, ProblemDetail, PlantUpdate>({
    mutationFn: async (payload) => {
      const { data, error, response } = await plantsUpdate({
        path: { plant_id: plantId },
        body: payload,
      });
      if (!response?.ok || !data) {
        return throwProblem(response, error);
      }
      return data;
    },
    onSuccess: (updated) => {
      // The PATCH response has no `intervals`, so merge rather than replace —
      // overwriting would blank the interval list until the next refetch.
      queryClient.setQueryData<PlantDetailOut>(qk.plants.detail(plantId), (previous) =>
        previous ? { ...previous, ...updated } : previous,
      );
      invalidatePlants(queryClient);
    },
  });
}

export function useDeletePlant() {
  const queryClient = useQueryClient();
  return useMutation<void, ProblemDetail, string>({
    mutationFn: async (plantId) => {
      const { error, response } = await plantsDelete({ path: { plant_id: plantId } });
      if (!response?.ok) {
        return throwProblem(response, error);
      }
    },
    onSuccess: () => invalidatePlants(queryClient),
  });
}

export function useAddInterval(plantId: string) {
  const queryClient = useQueryClient();
  return useMutation<CareIntervalOut, ProblemDetail, CareIntervalCreate>({
    mutationFn: async (payload) => {
      const { data, error, response } = await plantsAddInterval({
        path: { plant_id: plantId },
        body: payload,
      });
      if (!response?.ok || !data) {
        return throwProblem(response, error);
      }
      return data;
    },
    onSuccess: () => invalidatePlants(queryClient),
  });
}

export function useUpdateInterval(plantId: string) {
  const queryClient = useQueryClient();
  return useMutation<
    CareIntervalOut,
    ProblemDetail,
    { intervalId: string; payload: CareIntervalUpdate }
  >({
    mutationFn: async ({ intervalId, payload }) => {
      const { data, error, response } = await plantsUpdateInterval({
        path: { plant_id: plantId, interval_id: intervalId },
        body: payload,
      });
      if (!response?.ok || !data) {
        return throwProblem(response, error);
      }
      return data;
    },
    onSuccess: () => invalidatePlants(queryClient),
  });
}

export function useDeleteInterval(plantId: string) {
  const queryClient = useQueryClient();
  return useMutation<void, ProblemDetail, string>({
    mutationFn: async (intervalId) => {
      const { error, response } = await plantsDeleteInterval({
        path: { plant_id: plantId, interval_id: intervalId },
      });
      if (!response?.ok) {
        return throwProblem(response, error);
      }
    },
    onSuccess: () => invalidatePlants(queryClient),
  });
}

/**
 * Marking an action done. Not optimistic: the server decides the next due
 * date (completion date + interval), and guessing it client-side would show
 * the wrong date for a second whenever the completion is back-dated.
 */
export function useCompleteInterval(plantId: string) {
  const queryClient = useQueryClient();
  return useMutation<
    CompleteResult,
    ProblemDetail,
    { intervalId: string; payload: CompleteRequest }
  >({
    mutationFn: async ({ intervalId, payload }) => {
      const { data, error, response } = await plantsCompleteInterval({
        path: { plant_id: plantId, interval_id: intervalId },
        body: payload,
      });
      if (!response?.ok || !data) {
        return throwProblem(response, error);
      }
      return data;
    },
    onSuccess: () => invalidatePlants(queryClient),
  });
}

export function useSetPlantImage(plantId: string) {
  const queryClient = useQueryClient();
  return useMutation<PlantOut, ProblemDetail, File>({
    mutationFn: async (file) => {
      const { data, error, response } = await plantsSetImage({
        path: { plant_id: plantId },
        body: { file },
      });
      if (!response?.ok || !data) {
        return throwProblem(response, error);
      }
      return data;
    },
    onSuccess: () => invalidatePlants(queryClient),
  });
}

export function useDeletePlantImage(plantId: string) {
  const queryClient = useQueryClient();
  return useMutation<void, ProblemDetail, void>({
    mutationFn: async () => {
      const { error, response } = await plantsDeleteImage({ path: { plant_id: plantId } });
      if (!response?.ok) {
        return throwProblem(response, error);
      }
    },
    onSuccess: () => invalidatePlants(queryClient),
  });
}
