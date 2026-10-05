import { useNavigate } from '@tanstack/react-router';
import { CheckCircle2, XCircle } from 'lucide-react';
import { type FormEvent, type ReactElement, useState } from 'react';

import { useToast } from '../feedback/ToastProvider';
import { describeLearningError } from './useLearningMutations';
import {
  type NormalizedResult,
  type SessionKindName,
  useLearningSession,
} from './useLearningSession';

const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

interface SessionViewProps {
  kind: SessionKindName;
  courseId: string;
  sessionId: string;
}

const KIND_NOUN: Record<SessionKindName, string> = { quiz: 'quiz', exercise: 'exercise' };
const ANSWER_LABEL: Record<SessionKindName, string> = {
  quiz: 'Your answer',
  exercise: 'Your submission',
};

/**
 * M20 §10/§11: one component for both workflows, driven entirely by
 * `useLearningSession`'s already-normalized shape — mirrors the backend's
 * own `SessionKind`-parameterized engine (`service/sessions.py`) so the two
 * workflows can't drift on the client either.
 */
export function SessionView({ kind, courseId, sessionId }: SessionViewProps): ReactElement {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [answerText, setAnswerText] = useState('');
  const [followupText, setFollowupText] = useState('');
  const [followupHistory, setFollowupHistory] = useState<Array<{ role: string; content: string }>>(
    [],
  );
  const [lastResult, setLastResult] = useState<NormalizedResult | undefined>(undefined);

  const engine = useLearningSession(kind, sessionId);

  if (engine.sessionQuery.isPending) {
    return <p aria-busy="true">Loading…</p>;
  }
  if (engine.sessionQuery.isError || !engine.session) {
    return <p role="alert">Failed to load the {KIND_NOUN[kind]}.</p>;
  }

  const { session } = engine;

  function handleStart(): void {
    engine.start.mutate(undefined, {
      onError: (error) => showToast(describeLearningError(error), 'error'),
    });
  }

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    engine.submit.mutate(answerText, {
      onSuccess: (result) => {
        setLastResult(engine.normalizeResult(result));
        setAnswerText('');
        setFollowupHistory([]);
      },
      onError: (error) => showToast(describeLearningError(error), 'error'),
    });
  }

  function handleFollowup(event: FormEvent): void {
    event.preventDefault();
    const content = followupText;
    setFollowupHistory((prev) => [...prev, { role: 'user', content }]);
    setFollowupText('');
    engine.followup.mutate(content, {
      onSuccess: (data) =>
        setFollowupHistory((prev) => [...prev, { role: data.role, content: data.content }]),
      onError: (error) => showToast(describeLearningError(error), 'error'),
    });
  }

  function handleAdvance(): void {
    setLastResult(undefined);
    setFollowupHistory([]);
    engine.advance.mutate(undefined, {
      onError: (error) => showToast(describeLearningError(error), 'error'),
    });
  }

  if (session.status === 'draft') {
    return (
      <>
        <h1 className="mb-4 capitalize">{KIND_NOUN[kind]}</h1>
        <ul className="mb-4 flex flex-col gap-2">
          {engine.items.map((item, index) => (
            <li key={item.id} className="border-border bg-surface rounded-md border p-3 text-sm">
              {index + 1}. {item.promptText}
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={handleStart}
          disabled={engine.start.isPending}
          className={primaryButtonClass}
        >
          Start {KIND_NOUN[kind]}
        </button>
      </>
    );
  }

  if (session.status === 'completed') {
    const summary = engine.summary;
    return (
      <>
        <h1 className="mb-4 capitalize">{KIND_NOUN[kind]} complete</h1>
        {summary && (
          <div className="border-border bg-surface mb-4 rounded-md border p-4">
            <p className="text-text text-sm font-medium">
              {'overall_score' in summary
                ? `Score: ${Math.round(summary.overall_score * 100)}%`
                : `Pass rate: ${Math.round(summary.pass_rate * 100)}%`}
            </p>
            {summary.weakest_tag_ids.length > 0 && (
              <p className="text-text-muted mt-1 text-xs">
                {summary.weakest_tag_ids.length} weak area
                {summary.weakest_tag_ids.length === 1 ? '' : 's'} to review.
              </p>
            )}
          </div>
        )}
        <button
          type="button"
          onClick={() => void navigate({ to: '/learning/$courseId/path', params: { courseId } })}
          className={secondaryButtonClass}
        >
          Back to path
        </button>
      </>
    );
  }

  // in_progress
  const currentItem = engine.currentItem;
  return (
    <>
      <h1 className="mb-4 capitalize">{KIND_NOUN[kind]}</h1>

      {engine.currentItemQuery.isPending && <p aria-busy="true">Loading question…</p>}

      {currentItem && (
        <div className="border-border bg-surface mb-4 rounded-md border p-4">
          <p className="text-text mb-1 text-xs font-medium tracking-wide uppercase">
            Question {currentItem.orderIndex + 1}
          </p>
          <p className="text-text text-sm">{currentItem.promptText}</p>
          {currentItem.hintText && (
            <p className="text-text-muted mt-2 text-xs">Hint: {currentItem.hintText}</p>
          )}
        </div>
      )}

      {!lastResult && currentItem?.status === 'pending' && (
        <form onSubmit={handleSubmit} className="mb-4 flex flex-col gap-2">
          <label htmlFor="session-answer" className="text-text text-sm font-medium">
            {ANSWER_LABEL[kind]}
          </label>
          <textarea
            id="session-answer"
            required
            rows={5}
            value={answerText}
            onChange={(event) => setAnswerText(event.target.value)}
            className="border-border bg-surface rounded-sm border px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={engine.submit.isPending}
            className={`${primaryButtonClass} self-start`}
          >
            Submit
          </button>
        </form>
      )}

      {!lastResult && currentItem && currentItem.status !== 'pending' && (
        <p className="text-text-muted mb-4 text-sm">
          Already answered.{' '}
          <button type="button" onClick={handleAdvance} className="text-accent underline">
            Continue
          </button>
        </p>
      )}

      {lastResult && (
        <div className="mb-4 flex flex-col gap-3">
          <div
            className={`border-border bg-surface flex items-start gap-2 rounded-md border p-4 ${lastResult.succeeded ? 'border-success' : 'border-danger'}`}
          >
            {lastResult.succeeded ? (
              <CheckCircle2 className="text-success h-5 w-5 shrink-0" aria-hidden="true" />
            ) : (
              <XCircle className="text-danger h-5 w-5 shrink-0" aria-hidden="true" />
            )}
            <div>
              <p className="text-text text-sm font-medium">{lastResult.scoreLabel}</p>
              <p className="text-text-muted text-sm">{lastResult.feedbackText}</p>
            </div>
          </div>

          {followupHistory.length > 0 && (
            <ul className="flex flex-col gap-2">
              {followupHistory.map((message, index) => (
                <li
                  key={index}
                  className={`rounded-md border p-3 text-sm ${message.role === 'user' ? 'border-border bg-surface' : 'border-border bg-surface-sunken'}`}
                >
                  {message.content}
                </li>
              ))}
            </ul>
          )}

          <form onSubmit={handleFollowup} className="flex gap-2">
            <input
              type="text"
              placeholder="Ask a follow-up question…"
              value={followupText}
              onChange={(event) => setFollowupText(event.target.value)}
              className="border-border bg-surface min-w-0 flex-1 rounded-sm border px-3 py-2 text-sm"
            />
            <button
              type="submit"
              disabled={!followupText || engine.followup.isPending}
              className={secondaryButtonClass}
            >
              Ask
            </button>
          </form>

          <button
            type="button"
            onClick={handleAdvance}
            disabled={engine.advance.isPending}
            className={`${primaryButtonClass} self-start`}
          >
            Next
          </button>
        </div>
      )}
    </>
  );
}
