import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';

import {
  authListInvites,
  authListTokens,
  authMe,
  dashboardManifest,
  dashboardTiles,
  notesGet,
  notesList,
  plantsCalendar,
  plantsGet,
  plantsHistory,
  plantsList,
  settingsGet,
} from './generated';
import type { DashboardManifestResponse } from './generated';
import type { ProblemDetail } from './problem';
import { qk } from './queryKeys';

/**
 * The dashboard manifest is needed today by the app shell's nav (§12.2) and
 * by `_app`'s route loader (so `/settings/:domain` can validate a domain
 * without a network call, per §9) — well before M05 (the dashboard screen)
 * exists to "own" it. M05 should extend this file for the tiles/settings
 * queries it needs rather than duplicating a second manifest query
 * elsewhere; the query key and shape here are already the canonical ones.
 */
export function dashboardManifestQueryOptions() {
  return queryOptions({
    queryKey: qk.dashboard.manifest(),
    queryFn: async () => {
      const { data, error, response } = await dashboardManifest();
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load the dashboard manifest.');
      }
      return data;
    },
    // WEB-SPEC §10.2: ['dashboard','manifest'] — 10 min staleTime, no refetch on focus.
    staleTime: 10 * 60_000,
    refetchOnWindowFocus: false,
  });
}

/**
 * WEB-SPEC §9: `/settings/:domain` validates `domain` against modules that
 * actually have a settings panel — not just any module in the manifest —
 * without a network call. `routes/_app.settings.$domain.tsx` is the caller;
 * pulled out as a pure function so that route's `beforeLoad` and a future
 * `SettingsIndex` (M06, listing the same panels) share one definition of
 * "valid domain" rather than each re-deriving it from the manifest shape.
 */
export function settingsPanelDomains(manifest: DashboardManifestResponse): string[] {
  return manifest.modules
    .filter((module) => module.settings_panels.length > 0)
    .map((module) => module.domain);
}

/** §13.1's bulk fetch — one `TileData` per tile, on first render. */
export function dashboardTilesQueryOptions() {
  return queryOptions({
    queryKey: qk.dashboard.tiles(),
    queryFn: async () => {
      const { data, error, response } = await dashboardTiles();
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load dashboard tiles.');
      }
      return data;
    },
    // WEB-SPEC §10.2: ['dashboard','tiles'] — always stale, refetch on focus.
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
}

/** §14.1: current values for a domain's settings panel, secrets masked as `"***"`. */
export function settingsQueryOptions(domain: string) {
  return queryOptions({
    queryKey: qk.settings.domain(domain),
    queryFn: async () => {
      const { data, error, response } = await settingsGet({ path: { domain } });
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load settings.');
      }
      return data;
    },
    // WEB-SPEC §10.2: ['settings', domain] — 60s staleTime, no refetch on focus.
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}

/**
 * §14.1: "Only changed keys are sent" — not an optimization, it's what
 * keeps an untouched secret's `"***"` sentinel from ever being echoed back
 * (§14.4's own per-field omission handles the secret key itself; this is
 * the same principle applied to every other top-level field). Pulled out
 * as a pure function — `routes/_app.settings.$domain.tsx` can't export it
 * directly for testing without also disabling that route's own code
 * splitting (confirmed in M05: any non-`Route` export blocks
 * `@tanstack/router-plugin`'s per-route lazy chunk).
 */
export function filterDirtyValues(
  values: Record<string, unknown>,
  dirtyFields: Record<string, unknown>,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.keys(values)
      .filter((key) => dirtyFields[key])
      .map((key) => [key, values[key]]),
  );
}

// Appendix D, verbatim. `core.settings.decryption_failed` is a real operational
// signal (the server's encryption key changed) the user needs to escalate,
// not a generic retryable error — it does NOT go through the generic 5xx
// toast copy.
const DECRYPTION_FAILED_COPY =
  "This setting can't be read — the server's encryption key may have changed. Contact your administrator.";
const PERMISSION_DENIED_COPY = "You don't have permission to do that.";

export function describeSettingsError(problem: ProblemDetail): string {
  if (problem.code === 'core.settings.decryption_failed') {
    return DECRYPTION_FAILED_COPY;
  }
  if (problem.status === 403) {
    return PERMISSION_DENIED_COPY;
  }
  if (problem.status >= 500) {
    return `Something went wrong on the server. Reference: ${problem.request_id}`;
  }
  return problem.detail || 'Something went wrong. Please try again.';
}

/**
 * §15.1: `AuthProvider`'s bootstrap already seeds this cache key with a
 * full `MeResponse` (including `auth_method`, which the plain `UserOut` the
 * login/accept-invite paths store does not carry) when that path runs — see
 * `auth/AuthProvider.tsx`'s `onMeFetched` callback. This `queryFn` is the
 * fallback for every other case (a fresh login with no prior bootstrap, a
 * cold/expired cache): the account screen must work correctly either way,
 * not only right after a page-reload bootstrap.
 */
export function meQueryOptions() {
  return queryOptions({
    queryKey: qk.auth.me(),
    queryFn: async () => {
      const { data, error, response } = await authMe();
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load your account.');
      }
      return data;
    },
    // WEB-SPEC §10.2: ['auth','me'] — 5 min staleTime, no refetch on focus.
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}

/** §15.2: the caller's own API tokens (PATs) — name/prefix/created/last-used/expires, never the plaintext. */
export function tokensQueryOptions() {
  return queryOptions({
    queryKey: qk.auth.tokens(),
    queryFn: async () => {
      const { data, error, response } = await authListTokens();
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load API tokens.');
      }
      return data;
    },
    // WEB-SPEC §10.2: ['auth','tokens'] — 30s staleTime, no refetch on focus.
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

/** §15.3: pending invites — admin-only, enforced server-side (403) and by M04's route guard. */
export function invitesQueryOptions() {
  return queryOptions({
    queryKey: qk.auth.invites(),
    queryFn: async () => {
      const { data, error, response } = await authListInvites();
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load invites.');
      }
      return data;
    },
    // WEB-SPEC §10.2: ['auth','invites'] — 30s staleTime, no refetch on focus.
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

export interface NotesListFilters {
  q?: string;
  pinned?: boolean;
}

/**
 * §16.1/§10.5: cursor pagination via `useInfiniteQuery`, an explicit "Load
 * more" button rather than scroll-triggered loading. Server ordering
 * (`pinned DESC, created_at DESC, id DESC` — confirmed in
 * `src/disp/modules/notes/service.py`) is never re-sorted client-side.
 */
export function notesListInfiniteQueryOptions(filters: NotesListFilters) {
  return infiniteQueryOptions({
    queryKey: qk.notes.list(filters),
    queryFn: async ({ pageParam }: { pageParam: string | undefined }) => {
      const { data, error, response } = await notesList({
        query: {
          limit: 20,
          cursor: pageParam,
          q: filters.q || undefined,
          pinned: filters.pinned,
        },
      });
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load notes.');
      }
      return data;
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    // WEB-SPEC §10.2: ['notes','list',filters] — 30s staleTime, refetch on focus.
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });
}

/** §16.2: a single note. 404 is handled by the route's `loader`, which turns it into `notFound()`. */
export function noteDetailQueryOptions(noteId: string) {
  return queryOptions({
    queryKey: qk.notes.detail(noteId),
    queryFn: async () => {
      const { data, error, response } = await notesGet({ path: { note_id: noteId } });
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load the note.');
      }
      return data;
    },
    // WEB-SPEC §10.2: ['notes','detail',id] — 60s staleTime, refetch on focus.
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });
}

export interface PlantsListFilters {
  q?: string;
}

/**
 * M14 §4: `PlantOut` already carries the list's badge rollups (`due_count`,
 * `max_days_overdue`, `next_due_on`) — cursor pagination via
 * `useInfiniteQuery`, same shape as `notesListInfiniteQueryOptions`. A short
 * `staleTime` matters more here than for notes: those rollups are derived
 * against "today" server-side (M14 §1), so a longer cache risks showing a
 * due state that's already wrong after a date boundary.
 */
export function plantsListInfiniteQueryOptions(filters: PlantsListFilters) {
  return infiniteQueryOptions({
    queryKey: qk.plants.list(filters),
    queryFn: async ({ pageParam }: { pageParam: string | undefined }) => {
      const { data, error, response } = await plantsList({
        query: { limit: 20, cursor: pageParam, q: filters.q || undefined },
      });
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load plants.');
      }
      return data;
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });
}

/**
 * A plant plus its intervals. 404 is handled by the route's `loader`, which
 * turns it into `notFound()` — same pattern as `noteDetailQueryOptions`.
 * Short `staleTime` for the same reason as the list: `days_overdue` on each
 * interval is a server-computed fact about "today", not a stable property
 * of the row (M14 §1).
 */
export function plantDetailQueryOptions(plantId: string) {
  return queryOptions({
    queryKey: qk.plants.detail(plantId),
    queryFn: async () => {
      const { data, error, response } = await plantsGet({ path: { plant_id: plantId } });
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load the plant.');
      }
      return data;
    },
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });
}

/** M14 §5's detail-screen "recent history" list. */
export function plantHistoryQueryOptions(plantId: string) {
  return queryOptions({
    queryKey: qk.plants.history(plantId),
    queryFn: async () => {
      const { data, error, response } = await plantsHistory({ path: { plant_id: plantId } });
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load care history.');
      }
      return data;
    },
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });
}

/** M14 §5's calendar screen: one month's entries, keyed by `month` so each month is its own cache entry. */
export function plantCalendarQueryOptions(month: string) {
  return queryOptions({
    queryKey: qk.plants.calendar(month),
    queryFn: async () => {
      const { data, error, response } = await plantsCalendar({ query: { month } });
      if (!response?.ok || !data) {
        throw error ?? new Error('Failed to load the calendar.');
      }
      return data;
    },
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });
}
