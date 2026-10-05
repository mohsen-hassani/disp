import { type QueryKey, useMutation, useQueryClient } from '@tanstack/react-query';

import type {
  ChatMessageOut,
  ChatSessionCreate,
  ChatSessionOut,
  CourseCreate,
  CourseOut,
  DispCorePaginationPageNoteOut1,
  DispModulesLearningSchemasNoteCreate,
  DispModulesLearningSchemasNoteOut,
  DispModulesLearningSchemasNoteUpdate,
  ExerciseSessionOut,
  ExplainIn,
  ExplainOut,
  JobOut,
  PathItemUpdate,
  QuizSessionOut,
} from '../../api/generated';
import {
  learningApprovePath,
  learningCreateChat,
  learningCreateCourse,
  learningCreateExercise,
  learningCreateNote,
  learningCreateQuiz,
  learningCreateSource,
  learningDeleteNote,
  learningDeletePathItem,
  learningDeleteSource,
  learningExplainPathItem,
  learningGeneratePath,
  learningIndexCourse,
  learningSendChatMessage,
  learningUpdateNote,
  learningUpdatePathItem,
} from '../../api/generated';
import { type ProblemDetail, parseProblem } from '../../api/problem';
import { qk } from '../../api/queryKeys';

// Re-exported so every screen can import both the mutation hooks and the
// error describer from this one module, mirroring `usePlantMutations.ts`'s
// `describePlantError` (defined and exported from the mutations file itself
// there); `describeLearningError` happens to live in `api/queries.ts`
// instead since it was written alongside the other `learning` query options.
export { describeLearningError } from '../../api/queries';

const LEARNING_NOTES_PREFIX: QueryKey = ['learning', 'courses', 'notes'];
const LEARNING_TILE_KEY = qk.dashboard.tile('learning.next_up');

async function throwProblem(response: Response | undefined, error: unknown): Promise<never> {
  throw parseProblem(response ?? new Response(null, { status: 0 }), error);
}

function invalidateCourse(queryClient: ReturnType<typeof useQueryClient>, courseId: string) {
  void queryClient.invalidateQueries({ queryKey: qk.learning.courses.detail(courseId) });
}

// M20 §20's tile has no dedicated M14 §6-style rule of its own, but the same
// reasoning applies: any mutation that changes what's "next up" (a path
// getting approved, an item completing) must invalidate the tile explicitly,
// same as `usePlantMutations.ts`'s `invalidatePlantsTile`.
function invalidateTile(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: LEARNING_TILE_KEY });
}

// --- courses / sources -------------------------------------------------

export function useCreateCourse() {
  const queryClient = useQueryClient();
  return useMutation<CourseOut, ProblemDetail, CourseCreate>({
    mutationFn: async (payload) => {
      const { data, error, response } = await learningCreateCourse({ body: payload });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.learning.courses.list() });
    },
  });
}

interface CreateSourceVars {
  courseId: string;
  title: string;
  contentType: string;
  file?: File;
  rawText?: string;
}

export function useCreateSource() {
  const queryClient = useQueryClient();
  return useMutation<unknown, ProblemDetail, CreateSourceVars>({
    mutationFn: async ({ courseId, title, contentType, file, rawText }) => {
      const { data, error, response } = await learningCreateSource({
        path: { course_id: courseId },
        body: { title, content_type: contentType, file, raw_text: rawText },
      });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
    onSuccess: (_data, { courseId }) => {
      void queryClient.invalidateQueries({ queryKey: qk.learning.courses.sources(courseId) });
    },
  });
}

export function useDeleteSource() {
  const queryClient = useQueryClient();
  return useMutation<void, ProblemDetail, { sourceId: string; courseId: string }>({
    mutationFn: async ({ sourceId }) => {
      const { error, response } = await learningDeleteSource({ path: { source_id: sourceId } });
      if (!response?.ok) return throwProblem(response, error);
    },
    onSuccess: (_data, { courseId }) => {
      void queryClient.invalidateQueries({ queryKey: qk.learning.courses.sources(courseId) });
    },
  });
}

export function useIndexCourse() {
  const queryClient = useQueryClient();
  return useMutation<JobOut, ProblemDetail, string>({
    mutationFn: async (courseId) => {
      const { data, error, response } = await learningIndexCourse({
        path: { course_id: courseId },
      });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
    onSuccess: (_data, courseId) => invalidateCourse(queryClient, courseId),
  });
}

export function useGeneratePath() {
  const queryClient = useQueryClient();
  return useMutation<JobOut, ProblemDetail, string>({
    mutationFn: async (courseId) => {
      const { data, error, response } = await learningGeneratePath({
        path: { course_id: courseId },
      });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
    onSuccess: (_data, courseId) => {
      void queryClient.invalidateQueries({ queryKey: qk.learning.courses.path(courseId) });
    },
  });
}

export function useApprovePath() {
  const queryClient = useQueryClient();
  return useMutation<unknown, ProblemDetail, string>({
    mutationFn: async (courseId) => {
      const { data, error, response } = await learningApprovePath({
        path: { course_id: courseId },
      });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
    onSuccess: (_data, courseId) => {
      void queryClient.invalidateQueries({ queryKey: qk.learning.courses.path(courseId) });
      invalidateCourse(queryClient, courseId);
      invalidateTile(queryClient);
    },
  });
}

interface UpdatePathItemVars {
  pathItemId: string;
  courseId: string;
  payload: PathItemUpdate;
}

export function useUpdatePathItem() {
  const queryClient = useQueryClient();
  return useMutation<unknown, ProblemDetail, UpdatePathItemVars>({
    mutationFn: async ({ pathItemId, payload }) => {
      const { data, error, response } = await learningUpdatePathItem({
        path: { path_item_id: pathItemId },
        body: payload,
      });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
    onSuccess: (_data, { courseId }) => {
      void queryClient.invalidateQueries({ queryKey: qk.learning.courses.path(courseId) });
    },
  });
}

export function useDeletePathItem() {
  const queryClient = useQueryClient();
  return useMutation<void, ProblemDetail, { pathItemId: string; courseId: string }>({
    mutationFn: async ({ pathItemId }) => {
      const { error, response } = await learningDeletePathItem({
        path: { path_item_id: pathItemId },
      });
      if (!response?.ok) return throwProblem(response, error);
    },
    onSuccess: (_data, { courseId }) => {
      void queryClient.invalidateQueries({ queryKey: qk.learning.courses.path(courseId) });
    },
  });
}

export function useCreateQuizSession() {
  return useMutation<QuizSessionOut, ProblemDetail, string>({
    mutationFn: async (pathItemId) => {
      const { data, error, response } = await learningCreateQuiz({
        path: { path_item_id: pathItemId },
      });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
  });
}

export function useCreateExerciseSession() {
  return useMutation<ExerciseSessionOut, ProblemDetail, string>({
    mutationFn: async (pathItemId) => {
      const { data, error, response } = await learningCreateExercise({
        path: { path_item_id: pathItemId },
      });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
  });
}

export function useExplainPathItem() {
  return useMutation<ExplainOut, ProblemDetail, { pathItemId: string; payload: ExplainIn }>({
    mutationFn: async ({ pathItemId, payload }) => {
      const { data, error, response } = await learningExplainPathItem({
        path: { path_item_id: pathItemId },
        body: payload,
      });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
  });
}

// --- chat ----------------------------------------------------------------

export function useCreateChat() {
  const queryClient = useQueryClient();
  return useMutation<
    ChatSessionOut,
    ProblemDetail,
    { courseId: string; payload: ChatSessionCreate }
  >({
    mutationFn: async ({ courseId, payload }) => {
      const { data, error, response } = await learningCreateChat({
        path: { course_id: courseId },
        body: payload,
      });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
    onSuccess: (_data, { courseId }) => {
      void queryClient.invalidateQueries({ queryKey: qk.learning.courses.chats(courseId) });
    },
  });
}

export function useSendChatMessage() {
  const queryClient = useQueryClient();
  return useMutation<ChatMessageOut, ProblemDetail, { chatId: string; content: string }>({
    mutationFn: async ({ chatId, content }) => {
      const { data, error, response } = await learningSendChatMessage({
        path: { chat_id: chatId },
        body: { content },
      });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
    onSuccess: (_data, { chatId }) => {
      void queryClient.invalidateQueries({ queryKey: qk.learning.chats.messages(chatId) });
    },
  });
}

// --- notes -----------------------------------------------------------------

function invalidateNotes(queryClient: ReturnType<typeof useQueryClient>, courseId: string) {
  void queryClient.invalidateQueries({ queryKey: [...LEARNING_NOTES_PREFIX, courseId] });
}

export function useCreateNote() {
  const queryClient = useQueryClient();
  return useMutation<
    DispModulesLearningSchemasNoteOut,
    ProblemDetail,
    { courseId: string; payload: DispModulesLearningSchemasNoteCreate }
  >({
    mutationFn: async ({ courseId, payload }) => {
      const { data, error, response } = await learningCreateNote({
        path: { course_id: courseId },
        body: payload,
      });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
    onSuccess: (_data, { courseId }) => invalidateNotes(queryClient, courseId),
  });
}

export function useUpdateNote() {
  const queryClient = useQueryClient();
  return useMutation<
    DispModulesLearningSchemasNoteOut,
    ProblemDetail,
    { noteId: string; courseId: string; payload: DispModulesLearningSchemasNoteUpdate }
  >({
    mutationFn: async ({ noteId, payload }) => {
      const { data, error, response } = await learningUpdateNote({
        path: { note_id: noteId },
        body: payload,
      });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
    onSuccess: (_data, { courseId }) => invalidateNotes(queryClient, courseId),
  });
}

export function useDeleteNote() {
  const queryClient = useQueryClient();
  return useMutation<void, ProblemDetail, { noteId: string; courseId: string }>({
    mutationFn: async ({ noteId }) => {
      const { error, response } = await learningDeleteNote({ path: { note_id: noteId } });
      if (!response?.ok) return throwProblem(response, error);
    },
    onSuccess: (_data, { courseId }) => invalidateNotes(queryClient, courseId),
  });
}

export type { DispCorePaginationPageNoteOut1 as LearningNotesPage };
