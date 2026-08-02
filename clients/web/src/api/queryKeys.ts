// WEB-SPEC Appendix A, verbatim. No ad-hoc query-key literal is permitted
// anywhere else in the app — every useQuery/useMutation imports from here.
export const qk = {
  auth: {
    me: () => ['auth', 'me'] as const,
    tokens: () => ['auth', 'tokens'] as const,
    invites: () => ['auth', 'invites'] as const,
  },
  dashboard: {
    manifest: () => ['dashboard', 'manifest'] as const,
    tiles: () => ['dashboard', 'tiles'] as const,
    tile: (key: string) => ['dashboard', 'tile', key] as const,
  },
  settings: {
    domain: (domain: string) => ['settings', domain] as const,
  },
  notes: {
    all: () => ['notes'] as const,
    list: (f: { q?: string; pinned?: boolean }) => ['notes', 'list', f] as const,
    detail: (id: string) => ['notes', 'detail', id] as const,
  },
  // Every key starts with 'plants', so `actionDomainQueryKey('/api/plants/…')`
  // → ['plants'] prefix-matches all of them and a completed action can
  // invalidate the list, the detail, the due summary and the calendar at once.
  plants: {
    all: () => ['plants'] as const,
    list: (f: { q?: string }) => ['plants', 'list', f] as const,
    detail: (id: string) => ['plants', 'detail', id] as const,
    history: (id: string) => ['plants', 'history', id] as const,
    image: (id: string) => ['plants', 'image', id] as const,
    due: () => ['plants', 'due'] as const,
    calendar: (month: string) => ['plants', 'calendar', month] as const,
  },
} as const;
