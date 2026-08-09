import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { dashboardManifestQueryOptions } from '../api/queries';
import { navigableDomains } from '../modules/registry';

/**
 * Which module domains can be linked to: declared reachable by the server
 * (`client_nav`) *and* implemented by this client (`MODULE_SCREENS`).
 *
 * Reads the same manifest query the nav does — already in cache by the time
 * anything renders (`routes/_app.tsx`'s loader awaits it), so this never
 * fetches. Memoised because it returns a fresh `Set`, which would otherwise
 * be a new identity on every render for consumers that depend on it.
 */
export function useNavigableDomains(): ReadonlySet<string> {
  const manifestQuery = useQuery(dashboardManifestQueryOptions());
  const modules = manifestQuery.data?.modules;
  return useMemo(() => navigableDomains(modules), [modules]);
}
