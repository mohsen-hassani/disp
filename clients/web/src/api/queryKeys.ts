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
  plants: {
    all: () => ['plants'] as const,
    list: (f: { q?: string }) => ['plants', 'list', f] as const,
    detail: (id: string) => ['plants', 'detail', id] as const,
    history: (id: string) => ['plants', 'history', id] as const,
    calendar: (month: string) => ['plants', 'calendar', month] as const,
  },
  learning: {
    courses: {
      all: () => ['learning', 'courses'] as const,
      list: () => ['learning', 'courses', 'list'] as const,
      detail: (id: string) => ['learning', 'courses', 'detail', id] as const,
      sources: (id: string) => ['learning', 'courses', 'sources', id] as const,
      path: (id: string) => ['learning', 'courses', 'path', id] as const,
      progress: (id: string) => ['learning', 'courses', 'progress', id] as const,
      weakPoints: (id: string) => ['learning', 'courses', 'weak-points', id] as const,
      chats: (id: string) => ['learning', 'courses', 'chats', id] as const,
      notes: (id: string, f: { label?: string; pathItemId?: string }) =>
        ['learning', 'courses', 'notes', id, f] as const,
    },
    pathItems: {
      content: (id: string) => ['learning', 'path-items', 'content', id] as const,
    },
    jobs: {
      detail: (id: string) => ['learning', 'jobs', 'detail', id] as const,
    },
    sessions: {
      detail: (kind: 'quiz' | 'exercise', id: string) =>
        ['learning', 'sessions', kind, 'detail', id] as const,
      current: (kind: 'quiz' | 'exercise', id: string) =>
        ['learning', 'sessions', kind, 'current', id] as const,
      summary: (kind: 'quiz' | 'exercise', id: string) =>
        ['learning', 'sessions', kind, 'summary', id] as const,
    },
    chats: {
      messages: (id: string) => ['learning', 'chats', 'messages', id] as const,
    },
  },
} as const;
