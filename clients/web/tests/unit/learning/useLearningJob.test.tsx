import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type { JobOut } from '../../../src/api/generated';
import { useLearningJob } from '../../../src/hooks/useLearningJob';
import { jsonResponse } from '../auth/testUtils';

beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
});

let fetchSpy: ReturnType<typeof vi.spyOn> | undefined;
afterEach(() => {
  fetchSpy?.mockRestore();
  fetchSpy = undefined;
});

function job(overrides: Partial<JobOut> = {}): JobOut {
  return {
    id: 'job-1',
    course_id: 'course-1',
    kind: 'index',
    status: 'running',
    phase: 'segmenting',
    progress_current: 1,
    progress_total: 4,
    error_code: null,
    created_at: '2026-01-01T00:00:00Z',
    started_at: '2026-01-01T00:00:00Z',
    finished_at: null,
    ...overrides,
  };
}

/** M20 §23: the one client-side polling loop — stops on a terminal status and invalidates once. */
it('polls until the job reaches a terminal status, then invalidates the course and path queries once', async () => {
  let callCount = 0;
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
    callCount += 1;
    return jsonResponse(
      callCount === 1 ? job({ status: 'running' }) : job({ status: 'succeeded' }),
    );
  });

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
  function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }

  const { result } = renderHook(() => useLearningJob('job-1', 'course-1'), { wrapper });

  await waitFor(() => expect(result.current.data?.status).toBe('running'));
  await waitFor(() => expect(result.current.data?.status).toBe('succeeded'), { timeout: 5000 });

  await waitFor(() =>
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['learning', 'courses', 'detail', 'course-1'],
    }),
  );
  expect(invalidateSpy).toHaveBeenCalledWith({
    queryKey: ['learning', 'courses', 'path', 'course-1'],
  });
});

it('stays disabled with no jobId', () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch');
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }

  const { result } = renderHook(() => useLearningJob(undefined, 'course-1'), { wrapper });

  expect(result.current.fetchStatus).toBe('idle');
  expect(fetchSpy).not.toHaveBeenCalled();
});
