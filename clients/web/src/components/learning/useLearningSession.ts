import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type {
  ExerciseItemOut,
  ExerciseSessionOut,
  ExerciseSubmissionOut,
  ExerciseSummaryOut,
  FollowupOut,
  QuizAnswerOut,
  QuizItemOut,
  QuizSessionOut,
  QuizSummaryOut,
} from '../../api/generated';
import {
  learningAdvanceExercise,
  learningAdvanceQuiz,
  learningExerciseFollowup,
  learningExerciseSummary,
  learningGetCurrentQuestion,
  learningGetCurrentStep,
  learningGetExercise,
  learningGetQuiz,
  learningQuizFollowup,
  learningQuizSummary,
  learningStartExercise,
  learningStartQuiz,
  learningSubmitAnswer,
  learningSubmitStep,
} from '../../api/generated';
import { type ProblemDetail, parseProblem } from '../../api/problem';
import { qk } from '../../api/queryKeys';

async function throwProblem(response: Response | undefined, error: unknown): Promise<never> {
  throw parseProblem(response ?? new Response(null, { status: 0 }), error);
}

export type SessionKindName = 'quiz' | 'exercise';

/** A quiz question and an exercise step, collapsed into the one shape `SessionView` renders. */
export interface NormalizedItem {
  id: string;
  orderIndex: number;
  promptText: string;
  hintText: string | null;
  status: string;
}

/** A quiz answer and an exercise submission, collapsed into the one shape a result card renders. */
export interface NormalizedResult {
  id: string;
  succeeded: boolean;
  scoreLabel: string;
  feedbackText: string;
}

function normalizeItem(kind: SessionKindName, item: QuizItemOut | ExerciseItemOut): NormalizedItem {
  return {
    id: item.id,
    orderIndex: item.order_index,
    promptText:
      kind === 'quiz'
        ? (item as QuizItemOut).question_text
        : (item as ExerciseItemOut).instruction_text,
    hintText: kind === 'exercise' ? (item as ExerciseItemOut).hint_text : null,
    status: item.status,
  };
}

function normalizeResult(
  kind: SessionKindName,
  result: QuizAnswerOut | ExerciseSubmissionOut,
): NormalizedResult {
  if (kind === 'quiz') {
    const answer = result as QuizAnswerOut;
    return {
      id: answer.id,
      succeeded: answer.score >= 0.6,
      scoreLabel: `${Math.round(answer.score * 100)}%`,
      feedbackText: answer.feedback_text,
    };
  }
  const submission = result as ExerciseSubmissionOut;
  return {
    id: submission.id,
    succeeded: submission.passed,
    scoreLabel: submission.passed ? 'Passed' : 'Not yet',
    feedbackText: submission.feedback_text,
  };
}

/**
 * M20 §10/§11: quiz and exercise are one state machine on the server
 * (`service/sessions.py`'s `SessionKind`), differing only in field names and
 * whether completion is score-driven. This hook is that same idea on the
 * client — one engine, a `kind` discriminant, so `SessionView` never has to
 * know which workflow it's rendering.
 */
export function useLearningSession(kind: SessionKindName, sessionId: string) {
  const queryClient = useQueryClient();
  const isQuiz = kind === 'quiz';

  // A plain ternary between the two `queryOptions()` results still trips the
  // same overload-resolution problem `currentItemQuery`/`summaryQuery` hit
  // below (TS tries to match the whole `quiz | exercise` union against a
  // single overload) — so this is built inline for the same reason.
  const sessionQuery = useQuery<QuizSessionOut | ExerciseSessionOut, Error>({
    queryKey: qk.learning.sessions.detail(kind, sessionId),
    queryFn: async () => {
      if (isQuiz) {
        const { data, error, response } = await learningGetQuiz({
          path: { session_id: sessionId },
        });
        if (!response?.ok || !data) throw error ?? new Error('Failed to load the quiz.');
        return data;
      }
      const { data, error, response } = await learningGetExercise({
        path: { session_id: sessionId },
      });
      if (!response?.ok || !data) throw error ?? new Error('Failed to load the exercise.');
      return data;
    },
    staleTime: 0,
    refetchOnWindowFocus: false,
  });
  const session = sessionQuery.data;

  // Built inline (rather than via `queries.ts`'s per-kind factories) because
  // spreading a `quiz | exercise`-unioned `queryOptions()` result confuses
  // `useQuery`'s overload resolution — TS tries to match the whole union
  // against one overload instead of distributing over it.
  const currentItemQuery = useQuery<QuizItemOut | ExerciseItemOut, Error>({
    queryKey: qk.learning.sessions.current(kind, sessionId),
    queryFn: async () => {
      if (isQuiz) {
        const { data, error, response } = await learningGetCurrentQuestion({
          path: { session_id: sessionId },
        });
        if (!response?.ok || !data)
          throw error ?? new Error('Failed to load the current question.');
        return data;
      }
      const { data, error, response } = await learningGetCurrentStep({
        path: { session_id: sessionId },
      });
      if (!response?.ok || !data) throw error ?? new Error('Failed to load the current step.');
      return data;
    },
    enabled: session?.status === 'in_progress',
    staleTime: 0,
    refetchOnWindowFocus: false,
  });

  const summaryQuery = useQuery<QuizSummaryOut | ExerciseSummaryOut, Error>({
    queryKey: qk.learning.sessions.summary(kind, sessionId),
    queryFn: async () => {
      if (isQuiz) {
        const { data, error, response } = await learningQuizSummary({
          path: { session_id: sessionId },
        });
        if (!response?.ok || !data) throw error ?? new Error('Failed to load the quiz summary.');
        return data;
      }
      const { data, error, response } = await learningExerciseSummary({
        path: { session_id: sessionId },
      });
      if (!response?.ok || !data) throw error ?? new Error('Failed to load the exercise summary.');
      return data;
    },
    enabled: session?.status === 'completed',
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  function invalidateSession() {
    void queryClient.invalidateQueries({ queryKey: qk.learning.sessions.detail(kind, sessionId) });
    void queryClient.invalidateQueries({ queryKey: qk.learning.sessions.current(kind, sessionId) });
  }

  const startMutation = useMutation<QuizSessionOut | ExerciseSessionOut, ProblemDetail, void>({
    mutationFn: async () => {
      const { data, error, response } = isQuiz
        ? await learningStartQuiz({ path: { session_id: sessionId } })
        : await learningStartExercise({ path: { session_id: sessionId } });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
    onSuccess: invalidateSession,
  });

  const submitMutation = useMutation<QuizAnswerOut | ExerciseSubmissionOut, ProblemDetail, string>({
    mutationFn: async (text) => {
      const { data, error, response } = isQuiz
        ? await learningSubmitAnswer({
            path: { session_id: sessionId },
            body: { answer_text: text },
          })
        : await learningSubmitStep({
            path: { session_id: sessionId },
            body: { submission_text: text },
          });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
    onSuccess: invalidateSession,
  });

  const followupMutation = useMutation<FollowupOut, ProblemDetail, string>({
    mutationFn: async (content) => {
      const { data, error, response } = isQuiz
        ? await learningQuizFollowup({ path: { session_id: sessionId }, body: { content } })
        : await learningExerciseFollowup({ path: { session_id: sessionId }, body: { content } });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
  });

  const advanceMutation = useMutation<QuizSessionOut | ExerciseSessionOut, ProblemDetail, void>({
    mutationFn: async () => {
      const { data, error, response } = isQuiz
        ? await learningAdvanceQuiz({ path: { session_id: sessionId } })
        : await learningAdvanceExercise({ path: { session_id: sessionId } });
      if (!response?.ok || !data) return throwProblem(response, error);
      return data;
    },
    onSuccess: () => {
      invalidateSession();
      void queryClient.invalidateQueries({
        queryKey: qk.learning.sessions.summary(kind, sessionId),
      });
      // A completed quiz drives `path_item.completion_status` (§3.5), which
      // is exactly what the `learning.next_up` tile counts.
      void queryClient.invalidateQueries({ queryKey: qk.dashboard.tile('learning.next_up') });
    },
  });

  const items =
    (isQuiz ? (session as QuizSessionOut)?.questions : (session as ExerciseSessionOut)?.steps) ??
    [];
  const currentItem = currentItemQuery.data
    ? normalizeItem(kind, currentItemQuery.data as QuizItemOut | ExerciseItemOut)
    : undefined;

  return {
    session,
    sessionQuery,
    items: items.map((item) => normalizeItem(kind, item)),
    currentItem,
    currentItemQuery,
    summary: summaryQuery.data,
    summaryQuery,
    start: startMutation,
    submit: submitMutation,
    followup: followupMutation,
    advance: advanceMutation,
    normalizeResult: (result: QuizAnswerOut | ExerciseSubmissionOut) =>
      normalizeResult(kind, result),
  };
}
