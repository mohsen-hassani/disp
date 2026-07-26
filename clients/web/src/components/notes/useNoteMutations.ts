import {
  type InfiniteData,
  type QueryKey,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';

import type {
  NoteCreate,
  NoteOut,
  NoteUpdate,
  PageNoteOut,
  ShareRequest,
} from '../../api/generated';
import { notesCreate, notesDelete, notesShare, notesUpdate } from '../../api/generated';
import { type ProblemDetail, parseProblem } from '../../api/problem';
import { qk } from '../../api/queryKeys';

// WEB-SPEC §10.3: the list-key entry covers every filter combination —
// `qk.notes.list(f)` is `['notes','list',f]`, and TanStack Query's
// `invalidateQueries` prefix-matches, so this two-element key hits all of
// them without enumerating filters.
const NOTES_LIST_PREFIX: QueryKey = ['notes', 'list'];
const NOTES_TILE_KEY = qk.dashboard.tile('notes.latest');

function invalidateNotesList(queryClient: ReturnType<typeof useQueryClient>): void {
  void queryClient.invalidateQueries({ queryKey: NOTES_LIST_PREFIX });
}

function invalidateNotesTile(queryClient: ReturnType<typeof useQueryClient>): void {
  void queryClient.invalidateQueries({ queryKey: NOTES_TILE_KEY });
}

async function throwProblem(response: Response | undefined, error: unknown): Promise<never> {
  throw parseProblem(response ?? new Response(null, { status: 0 }), error);
}

async function createOrThrow(payload: NoteCreate): Promise<NoteOut> {
  const { data, error, response } = await notesCreate({ body: payload });
  if (!response?.ok || !data) {
    return throwProblem(response, error);
  }
  return data;
}

async function updateOrThrow(noteId: string, payload: NoteUpdate): Promise<NoteOut> {
  const { data, error, response } = await notesUpdate({ path: { note_id: noteId }, body: payload });
  if (!response?.ok || !data) {
    return throwProblem(response, error);
  }
  return data;
}

async function deleteOrThrow(noteId: string): Promise<void> {
  const { error, response } = await notesDelete({ path: { note_id: noteId } });
  if (!response?.ok) {
    return throwProblem(response, error);
  }
}

async function shareOrThrow(noteId: string, payload: ShareRequest): Promise<void> {
  const { error, response } = await notesShare({ path: { note_id: noteId }, body: payload });
  if (!response?.ok) {
    return throwProblem(response, error);
  }
}

/** §16.3: creation is not one of §10.4's three optimistic exceptions — pending state, wait for the server. */
export function useCreateNote() {
  const queryClient = useQueryClient();
  return useMutation<NoteOut, ProblemDetail, NoteCreate>({
    mutationFn: createOrThrow,
    onSuccess: () => {
      invalidateNotesList(queryClient);
      invalidateNotesTile(queryClient);
    },
  });
}

/** §16.2's inline body edit — plain pending mutation, writes the server's response straight into the detail cache. */
export function useUpdateNote(noteId: string) {
  const queryClient = useQueryClient();
  return useMutation<NoteOut, ProblemDetail, NoteUpdate>({
    mutationFn: (payload) => updateOrThrow(noteId, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(qk.notes.detail(noteId), data);
      invalidateNotesList(queryClient);
      invalidateNotesTile(queryClient);
    },
  });
}

interface TogglePinnedVars {
  id: string;
  pinned: boolean;
}

interface TogglePinnedContext {
  previousDetail?: NoteOut;
  previousList?: InfiniteData<PageNoteOut>;
}

/**
 * §10.4 exception 1. `listKey` is the *currently rendered* list query's
 * exact key (filters and all) — passed by the list screen so the optimistic
 * splice only ever touches the one page the user is looking at; other
 * filter combinations are left to `onSettled`'s blanket invalidation. The
 * detail page passes no `listKey` (there is no rendered list to touch) and
 * still gets a correct optimistic flip of its own cached note.
 */
export function useTogglePinned(listKey?: QueryKey) {
  const queryClient = useQueryClient();
  return useMutation<NoteOut, ProblemDetail, TogglePinnedVars, TogglePinnedContext>({
    mutationFn: ({ id, pinned }) => updateOrThrow(id, { pinned }),
    onMutate: async ({ id, pinned }) => {
      await queryClient.cancelQueries({ queryKey: qk.notes.detail(id) });
      const previousDetail = queryClient.getQueryData<NoteOut>(qk.notes.detail(id));
      if (previousDetail) {
        queryClient.setQueryData(qk.notes.detail(id), { ...previousDetail, pinned });
      }

      let previousList: InfiniteData<PageNoteOut> | undefined;
      if (listKey) {
        await queryClient.cancelQueries({ queryKey: listKey });
        previousList = queryClient.getQueryData<InfiniteData<PageNoteOut>>(listKey);
        if (previousList) {
          queryClient.setQueryData<InfiniteData<PageNoteOut>>(listKey, {
            ...previousList,
            pages: previousList.pages.map((page) => ({
              ...page,
              items: page.items.map((item) => (item.id === id ? { ...item, pinned } : item)),
            })),
          });
        }
      }

      return { previousDetail, previousList };
    },
    onError: (_error, { id }, context) => {
      if (context?.previousDetail) {
        queryClient.setQueryData(qk.notes.detail(id), context.previousDetail);
      }
      if (listKey && context?.previousList) {
        queryClient.setQueryData(listKey, context.previousList);
      }
    },
    onSettled: (_data, _error, { id }) => {
      invalidateNotesList(queryClient);
      void queryClient.invalidateQueries({ queryKey: qk.notes.detail(id) });
      invalidateNotesTile(queryClient);
    },
  });
}

interface DeleteNoteContext {
  previousList?: InfiniteData<PageNoteOut>;
}

/** §10.4 exception 2. The detail cache is only removed on confirmed success, never optimistically. */
export function useDeleteNote(listKey?: QueryKey) {
  const queryClient = useQueryClient();
  return useMutation<void, ProblemDetail, string, DeleteNoteContext>({
    mutationFn: deleteOrThrow,
    onMutate: async (id) => {
      let previousList: InfiniteData<PageNoteOut> | undefined;
      if (listKey) {
        await queryClient.cancelQueries({ queryKey: listKey });
        previousList = queryClient.getQueryData<InfiniteData<PageNoteOut>>(listKey);
        if (previousList) {
          queryClient.setQueryData<InfiniteData<PageNoteOut>>(listKey, {
            ...previousList,
            pages: previousList.pages.map((page) => ({
              ...page,
              items: page.items.filter((item) => item.id !== id),
            })),
          });
        }
      }
      return { previousList };
    },
    onError: (_error, _id, context) => {
      if (listKey && context?.previousList) {
        queryClient.setQueryData(listKey, context.previousList);
      }
    },
    onSuccess: (_data, id) => {
      queryClient.removeQueries({ queryKey: qk.notes.detail(id) });
    },
    onSettled: () => {
      invalidateNotesList(queryClient);
      invalidateNotesTile(queryClient);
    },
  });
}

/** §16.4: sharing only ever invalidates the detail key (§10.3) — never the list, which shows no share state. */
export function useShareNote(noteId: string) {
  const queryClient = useQueryClient();
  return useMutation<void, ProblemDetail, ShareRequest>({
    mutationFn: (payload) => shareOrThrow(noteId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.notes.detail(noteId) });
    },
  });
}

// §7.3's table, the subset relevant to a note mutation with no per-field mapping of its own.
export function describeNoteError(problem: ProblemDetail): string {
  if (problem.code === 'acl.forbidden') {
    return "You don't have permission to do that.";
  }
  if (problem.status >= 500) {
    return `Something went wrong on the server. Reference: ${problem.request_id}`;
  }
  return problem.detail || 'Something went wrong. Please try again.';
}
