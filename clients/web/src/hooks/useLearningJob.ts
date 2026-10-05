import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import type { JobOut } from '../api/generated';
import { learningJobQueryOptions } from '../api/queries';
import { qk } from '../api/queryKeys';

const POLL_INTERVAL_MS = 2000;
const TERMINAL_STATUSES = new Set(['succeeded', 'failed']);

/**
 * M20 §23: "job polling in one hook, with a refetchInterval that stops on a
 * terminal status" — the client's only polling loop. `jobId` may be
 * `undefined` while no job has been kicked off yet (e.g. before the first
 * index/generate-path call); the query stays disabled in that case.
 *
 * On reaching a terminal status, invalidates the course/path queries once
 * so the screen that triggered the job picks up its result without a
 * manual refresh, and calls `onSettled` (if given) exactly once with the
 * final job — a `status: 'failed'` job (e.g. `DISP_LLM_ENABLED=false`, per
 * M20's own documented degraded mode) would otherwise revert the triggering
 * button to idle with no explanation at all.
 */
export function useLearningJob(
  jobId: string | undefined,
  courseId: string | undefined,
  onSettled?: (job: JobOut) => void,
) {
  const queryClient = useQueryClient();
  const settledRef = useRef<string | undefined>(undefined);

  const query = useQuery({
    ...learningJobQueryOptions(jobId ?? ''),
    enabled: Boolean(jobId),
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status && TERMINAL_STATUSES.has(status) ? false : POLL_INTERVAL_MS;
    },
    refetchIntervalInBackground: false,
  });

  useEffect(() => {
    const job = query.data;
    if (!jobId || !job || !TERMINAL_STATUSES.has(job.status) || settledRef.current === jobId) {
      return;
    }
    settledRef.current = jobId;
    if (courseId) {
      void queryClient.invalidateQueries({ queryKey: qk.learning.courses.detail(courseId) });
      void queryClient.invalidateQueries({ queryKey: qk.learning.courses.path(courseId) });
    }
    onSettled?.(job);
  }, [jobId, query.data, courseId, queryClient, onSettled]);

  return query;
}
