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

// WEB-SPEC §10.3-style prefix match: `qk.plants.list(f)` is
// `['plants','list',f]`, so this two-element key invalidates every filter
// combination without enumerating them.
const PLANTS_LIST_PREFIX: QueryKey = ['plants', 'list'];
const PLANTS_TILE_KEY = qk.dashboard.tile('plants.due');

function invalidatePlantsList(queryClient: ReturnType<typeof useQueryClient>): void {
  void queryClient.invalidateQueries({ queryKey: PLANTS_LIST_PREFIX });
}

function invalidatePlantsTile(queryClient: ReturnType<typeof useQueryClient>): void {
  void queryClient.invalidateQueries({ queryKey: PLANTS_TILE_KEY });
}

/**
 * M14 §6: "Every plants mutation must invalidate the list prefix, the
 * affected detail(id), and qk.dashboard.tile('plants.due')" — a tile
 * *action* gets this for free via `actionDomainQueryKey`, but a screen
 * mutation (everything in this file) has no such help and must do it
 * explicitly, or the dashboard count contradicts the screen the user just
 * acted on.
 */
function invalidateAffected(queryClient: ReturnType<typeof useQueryClient>, plantId: string): void {
  invalidatePlantsList(queryClient);
  void queryClient.invalidateQueries({ queryKey: qk.plants.detail(plantId) });
  invalidatePlantsTile(queryClient);
}

async function throwProblem(response: Response | undefined, error: unknown): Promise<never> {
  throw parseProblem(response ?? new Response(null, { status: 0 }), error);
}

async function createOrThrow(payload: PlantCreate): Promise<PlantOut> {
  const { data, error, response } = await plantsCreate({ body: payload });
  if (!response?.ok || !data) {
    return throwProblem(response, error);
  }
  return data;
}

async function updateOrThrow(plantId: string, payload: PlantUpdate): Promise<PlantOut> {
  const { data, error, response } = await plantsUpdate({
    path: { plant_id: plantId },
    body: payload,
  });
  if (!response?.ok || !data) {
    return throwProblem(response, error);
  }
  return data;
}

async function deleteOrThrow(plantId: string): Promise<void> {
  const { error, response } = await plantsDelete({ path: { plant_id: plantId } });
  if (!response?.ok) {
    return throwProblem(response, error);
  }
}

async function addIntervalOrThrow(
  plantId: string,
  payload: CareIntervalCreate,
): Promise<CareIntervalOut> {
  const { data, error, response } = await plantsAddInterval({
    path: { plant_id: plantId },
    body: payload,
  });
  if (!response?.ok || !data) {
    return throwProblem(response, error);
  }
  return data;
}

async function updateIntervalOrThrow(
  plantId: string,
  intervalId: string,
  payload: CareIntervalUpdate,
): Promise<CareIntervalOut> {
  const { data, error, response } = await plantsUpdateInterval({
    path: { plant_id: plantId, interval_id: intervalId },
    body: payload,
  });
  if (!response?.ok || !data) {
    return throwProblem(response, error);
  }
  return data;
}

async function deleteIntervalOrThrow(plantId: string, intervalId: string): Promise<void> {
  const { error, response } = await plantsDeleteInterval({
    path: { plant_id: plantId, interval_id: intervalId },
  });
  if (!response?.ok) {
    return throwProblem(response, error);
  }
}

async function completeIntervalOrThrow(
  plantId: string,
  intervalId: string,
  payload: CompleteRequest,
): Promise<CompleteResult> {
  const { data, error, response } = await plantsCompleteInterval({
    path: { plant_id: plantId, interval_id: intervalId },
    body: payload,
  });
  if (!response?.ok || !data) {
    return throwProblem(response, error);
  }
  return data;
}

async function setImageOrThrow(plantId: string, file: File): Promise<PlantOut> {
  const { data, error, response } = await plantsSetImage({
    path: { plant_id: plantId },
    body: { file },
  });
  if (!response?.ok || !data) {
    return throwProblem(response, error);
  }
  return data;
}

async function deleteImageOrThrow(plantId: string): Promise<void> {
  const { error, response } = await plantsDeleteImage({ path: { plant_id: plantId } });
  if (!response?.ok) {
    return throwProblem(response, error);
  }
}

/** M14 §5's create form — not one of §10.4's optimistic exceptions, plain pending mutation. */
export function useCreatePlant() {
  const queryClient = useQueryClient();
  return useMutation<PlantOut, ProblemDetail, PlantCreate>({
    mutationFn: createOrThrow,
    onSuccess: () => {
      invalidatePlantsList(queryClient);
      invalidatePlantsTile(queryClient);
    },
  });
}

export function useUpdatePlant(plantId: string) {
  const queryClient = useQueryClient();
  return useMutation<PlantOut, ProblemDetail, PlantUpdate>({
    mutationFn: (payload) => updateOrThrow(plantId, payload),
    onSuccess: (data) => {
      queryClient.setQueryData<PlantDetailOut>(qk.plants.detail(plantId), (prev) =>
        prev ? { ...prev, ...data } : prev,
      );
      invalidateAffected(queryClient, plantId);
    },
  });
}

export function useDeletePlant() {
  const queryClient = useQueryClient();
  return useMutation<void, ProblemDetail, string>({
    mutationFn: deleteOrThrow,
    onSuccess: (_data, plantId) => {
      queryClient.removeQueries({ queryKey: qk.plants.detail(plantId) });
      invalidatePlantsList(queryClient);
      invalidatePlantsTile(queryClient);
    },
  });
}

interface AddIntervalVars {
  plantId: string;
  payload: CareIntervalCreate;
}

export function useAddInterval() {
  const queryClient = useQueryClient();
  return useMutation<CareIntervalOut, ProblemDetail, AddIntervalVars>({
    mutationFn: ({ plantId, payload }) => addIntervalOrThrow(plantId, payload),
    onSuccess: (_data, { plantId }) => invalidateAffected(queryClient, plantId),
  });
}

interface UpdateIntervalVars {
  plantId: string;
  intervalId: string;
  payload: CareIntervalUpdate;
}

export function useUpdateInterval() {
  const queryClient = useQueryClient();
  return useMutation<CareIntervalOut, ProblemDetail, UpdateIntervalVars>({
    mutationFn: ({ plantId, intervalId, payload }) =>
      updateIntervalOrThrow(plantId, intervalId, payload),
    onSuccess: (_data, { plantId }) => invalidateAffected(queryClient, plantId),
  });
}

interface DeleteIntervalVars {
  plantId: string;
  intervalId: string;
}

export function useDeleteInterval() {
  const queryClient = useQueryClient();
  return useMutation<void, ProblemDetail, DeleteIntervalVars>({
    mutationFn: ({ plantId, intervalId }) => deleteIntervalOrThrow(plantId, intervalId),
    onSuccess: (_data, { plantId }) => invalidateAffected(queryClient, plantId),
  });
}

interface CompleteIntervalVars {
  plantId: string;
  intervalId: string;
  payload: CompleteRequest;
}

/**
 * M14 §1's central invariant: this never predicts `next_due_on` itself. The
 * server's returned `interval` (already recomputed from the completion
 * date, not the due date) is written straight into the cached detail so the
 * row updates instantly with the real value; the plant-level rollups
 * (`due_count`, `max_days_overdue`), which this response doesn't carry, are
 * left to the detail/list invalidation below rather than guessed locally.
 */
export function useCompleteInterval() {
  const queryClient = useQueryClient();
  return useMutation<CompleteResult, ProblemDetail, CompleteIntervalVars>({
    mutationFn: ({ plantId, intervalId, payload }) =>
      completeIntervalOrThrow(plantId, intervalId, payload),
    onSuccess: (result, { plantId }) => {
      queryClient.setQueryData<PlantDetailOut>(qk.plants.detail(plantId), (prev) =>
        prev
          ? {
              ...prev,
              intervals: prev.intervals.map((interval) =>
                interval.id === result.interval.id ? result.interval : interval,
              ),
            }
          : prev,
      );
      void queryClient.invalidateQueries({ queryKey: qk.plants.history(plantId) });
      invalidateAffected(queryClient, plantId);
    },
  });
}

interface SetImageVars {
  plantId: string;
  file: File;
}

export function useSetPlantImage() {
  const queryClient = useQueryClient();
  return useMutation<PlantOut, ProblemDetail, SetImageVars>({
    mutationFn: ({ plantId, file }) => setImageOrThrow(plantId, file),
    onSuccess: (_data, { plantId }) => invalidateAffected(queryClient, plantId),
  });
}

export function useDeletePlantImage() {
  const queryClient = useQueryClient();
  return useMutation<void, ProblemDetail, string>({
    mutationFn: deleteImageOrThrow,
    onSuccess: (_data, plantId) => invalidateAffected(queryClient, plantId),
  });
}

// M14 §6's counterpart to `describeNoteError` — `plants.future_date` /
// `plants.date_too_old` (both 400s from completing/back-dating an interval)
// are deliberately left out: those are surfaced inline next to the date
// field they belong to, not as a generic toast (M14 §5, §7 case 3).
export function describePlantError(problem: ProblemDetail): string {
  if (problem.code === 'acl.forbidden') {
    return "You don't have permission to do that.";
  }
  if (problem.code === 'plants.no_image') {
    return "This plant's photo is missing.";
  }
  if (problem.status >= 500) {
    return `Something went wrong on the server. Reference: ${problem.request_id}`;
  }
  return problem.detail || 'Something went wrong. Please try again.';
}
