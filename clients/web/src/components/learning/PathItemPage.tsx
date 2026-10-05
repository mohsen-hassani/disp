import { useQuery } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { PenLine, Sparkles } from 'lucide-react';
import { type ReactElement, useState } from 'react';

import { learningPathItemContentQueryOptions } from '../../api/queries';
import { useToast } from '../feedback/ToastProvider';
import {
  describeLearningError,
  useCreateExerciseSession,
  useCreateQuizSession,
  useExplainPathItem,
} from './useLearningMutations';

const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

const EXPLAIN_MODES: Array<{ value: string; label: string }> = [
  { value: 'explain', label: 'Explain differently' },
  { value: 'guide', label: 'Guide me step by step' },
  { value: 'summarize', label: 'Summarize' },
];

interface PathItemPageProps {
  courseId: string;
  itemId: string;
}

/** M20 §23: `/learning/$courseId/items/$itemId` — the §3.1-joined lesson content, plus explain/quiz/exercise entry points. */
export function PathItemPage({ courseId, itemId }: PathItemPageProps): ReactElement {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [explanation, setExplanation] = useState<string | undefined>(undefined);

  const contentQuery = useQuery(learningPathItemContentQueryOptions(itemId));
  const explain = useExplainPathItem();
  const createQuiz = useCreateQuizSession();
  const createExercise = useCreateExerciseSession();

  if (contentQuery.isPending) {
    return <p aria-busy="true">Loading…</p>;
  }
  if (contentQuery.isError || !contentQuery.data) {
    return <p role="alert">Failed to load this lesson.</p>;
  }

  const { path_item: pathItem, sections } = contentQuery.data;

  function handleExplain(mode: string): void {
    setExplanation(undefined);
    explain.mutate(
      { pathItemId: itemId, payload: { mode } },
      {
        onSuccess: (data) => setExplanation(data.content),
        onError: (error) => showToast(describeLearningError(error), 'error'),
      },
    );
  }

  function handleStartQuiz(): void {
    createQuiz.mutate(itemId, {
      onSuccess: (session) =>
        void navigate({
          to: '/learning/$courseId/quiz/$sessionId',
          params: { courseId, sessionId: session.id },
        }),
      onError: (error) => showToast(describeLearningError(error), 'error'),
    });
  }

  function handleStartExercise(): void {
    createExercise.mutate(itemId, {
      onSuccess: (session) =>
        void navigate({
          to: '/learning/$courseId/exercise/$sessionId',
          params: { courseId, sessionId: session.id },
        }),
      onError: (error) => showToast(describeLearningError(error), 'error'),
    });
  }

  return (
    <>
      <h1 className="mb-4">{pathItem.title}</h1>

      <div className="mb-6 flex flex-col gap-6">
        {sections.map((section) => (
          <div key={section.id}>
            <p className="text-text-muted mb-1 text-xs font-medium tracking-wide uppercase">
              {section.heading_path}
            </p>
            <p className="text-text text-sm whitespace-pre-wrap">{section.content_text}</p>
          </div>
        ))}
      </div>

      <div className="mb-6 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleStartQuiz}
          disabled={createQuiz.isPending}
          className={primaryButtonClass}
        >
          Start quiz
        </button>
        <button
          type="button"
          onClick={handleStartExercise}
          disabled={createExercise.isPending}
          className={primaryButtonClass}
        >
          Start exercise
        </button>
      </div>

      <div className="border-border bg-surface rounded-md border p-4">
        <h2 className="mb-2 inline-flex items-center gap-1.5 text-sm font-medium">
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          Need help with this lesson?
        </h2>
        <div className="mb-3 flex flex-wrap gap-2">
          {EXPLAIN_MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              onClick={() => handleExplain(m.value)}
              disabled={explain.isPending}
              className={secondaryButtonClass}
            >
              {m.label}
            </button>
          ))}
        </div>
        {explain.isPending && (
          <p aria-busy="true" className="text-text-muted text-sm">
            Thinking…
          </p>
        )}
        {explanation && (
          <p className="text-text text-sm whitespace-pre-wrap">
            <PenLine className="mr-1 inline h-3.5 w-3.5" aria-hidden="true" />
            {explanation}
          </p>
        )}
      </div>
    </>
  );
}
