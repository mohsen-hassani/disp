import type { ReactElement } from 'react';

interface SavedDataLabelProps {
  /** Callers compute this themselves — typically `isOffline && query.isSuccess` — see `useOfflineState`. */
  show: boolean;
}

/**
 * §18.5: "Data rendered from cache while offline is labelled with a subtle
 * 'Showing saved data' line in each affected view." Each screen wires this
 * in with its own visibility condition — a query that has data while
 * offline is, by construction, serving what the service worker cached,
 * since nothing else could have produced a successful response.
 */
export function SavedDataLabel({ show }: SavedDataLabelProps): ReactElement | null {
  if (!show) {
    return null;
  }
  return <p className="text-text-muted mb-2 text-xs">Showing saved data.</p>;
}
