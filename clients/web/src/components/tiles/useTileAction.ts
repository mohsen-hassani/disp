import { useMutation, useQueryClient } from '@tanstack/react-query';

import { client } from '../../api/client';
import { type ProblemDetail, parseProblem } from '../../api/problem';
import { qk } from '../../api/queryKeys';
import { actionDomainQueryKey } from './tileLinks';

export interface TileActionError {
  problem: ProblemDetail;
  /** Present only for 429 responses, per the `Retry-After` header — mirrors AuthProvider.tsx's shape. */
  retryAfterSeconds?: number;
}

export interface RunTileActionParams {
  method: 'POST' | 'PATCH' | 'DELETE';
  path: string;
  body?: unknown;
}

function toActionError(response: Response | undefined, body: unknown): TileActionError {
  if (!response) {
    return {
      problem: {
        type: 'about:blank',
        title: 'Network error',
        status: 0,
        detail: 'Could not reach the server.',
        instance: '',
        code: 'network_error',
        request_id: '',
      },
    };
  }
  const problem = parseProblem(response, body);
  const retryAfterHeader = response.headers.get('Retry-After');
  const retryAfterSeconds = retryAfterHeader === null ? undefined : Number(retryAfterHeader);
  return {
    problem,
    retryAfterSeconds:
      retryAfterSeconds !== undefined && Number.isFinite(retryAfterSeconds)
        ? retryAfterSeconds
        : undefined,
  };
}

// §13.6: fires an arbitrary `TileAction` (method/path are server-declared,
// not tied to any generated SDK function) through the same client
// interceptors as everything else (auth header, 401 refresh), then
// invalidates the tile's own key plus the path-derived domain key.
export function useTileAction(tileKey: string) {
  const queryClient = useQueryClient();

  return useMutation<void, TileActionError, RunTileActionParams>({
    mutationFn: async ({ method, path, body }) => {
      const { error, response } = await client.request({ method, url: path, body });
      if (!response?.ok) {
        throw toActionError(response, error);
      }
    },
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: qk.dashboard.tile(tileKey) });
      const domainKey = actionDomainQueryKey(variables.path);
      if (domainKey.length > 0) {
        void queryClient.invalidateQueries({ queryKey: domainKey });
      }
    },
  });
}

// §7.3's table, the subset relevant to a single-button action with no
// per-field mapping of its own.
export function describeActionError(error: TileActionError): string {
  const { problem, retryAfterSeconds } = error;
  if (problem.code === 'acl.forbidden') {
    return "You don't have permission to do that.";
  }
  if (problem.status === 429) {
    return retryAfterSeconds ? `Try again in ${retryAfterSeconds}s.` : 'Try again shortly.';
  }
  if (problem.status >= 500) {
    return `Something went wrong on the server. Reference: ${problem.request_id}`;
  }
  return problem.detail || 'Something went wrong. Please try again.';
}
