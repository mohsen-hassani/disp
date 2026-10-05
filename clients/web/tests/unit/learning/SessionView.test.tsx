import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type { QuizItemOut, QuizSessionOut } from '../../../src/api/generated';
import { SessionView } from '../../../src/components/learning/SessionView';
import { jsonResponse } from '../auth/testUtils';
import { renderLearning, routedFetch } from './testUtils';

beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
});

let fetchSpy: ReturnType<typeof vi.spyOn>;
afterEach(() => {
  fetchSpy?.mockRestore();
});

function question(overrides: Partial<QuizItemOut> = {}): QuizItemOut {
  return {
    id: 'question-1',
    order_index: 0,
    question_text: 'What does the borrow checker enforce?',
    target_tag_ids: [],
    status: 'pending',
    ...overrides,
  };
}

function session(overrides: Partial<QuizSessionOut> = {}): QuizSessionOut {
  return {
    id: 'session-1',
    path_item_id: 'item-1',
    status: 'draft',
    current_question_index: 0,
    created_at: '2026-01-01T00:00:00Z',
    started_at: null,
    completed_at: null,
    questions: [question()],
    ...overrides,
  };
}

/**
 * M20 §10/§11: this is the client-side counterpart of the backend's
 * parametrized `test_learning_sessions.py` suite — one flow (draft → start →
 * submit → advance → completed) exercised through `SessionView`, which is
 * itself kind-agnostic. Only the quiz kind is driven here since the two
 * kinds share every line of `SessionView`/`useLearningSession`; a second,
 * exercise-flavored run would duplicate assertions without covering new code.
 */
it('drives a quiz from draft through completion', async () => {
  let current = session();
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch(async (method, path, request) => {
      if (method === 'GET' && path === '/api/learning/quizzes/session-1') {
        return jsonResponse(current);
      }
      if (method === 'POST' && path === '/api/learning/quizzes/session-1/start') {
        current = { ...current, status: 'in_progress', started_at: '2026-01-01T00:01:00Z' };
        return jsonResponse(current);
      }
      if (method === 'GET' && path === '/api/learning/quizzes/session-1/current') {
        return jsonResponse(current.questions[current.current_question_index]);
      }
      if (method === 'POST' && path === '/api/learning/quizzes/session-1/submit') {
        const body = (await request.clone().json()) as { answer_text: string };
        expect(body.answer_text).toBe('It enforces memory safety without a garbage collector.');
        current = {
          ...current,
          questions: current.questions.map((q, i) =>
            i === current.current_question_index ? { ...q, status: 'answered' } : q,
          ),
        };
        return jsonResponse({
          id: 'answer-1',
          question_id: 'question-1',
          answer_text: body.answer_text,
          score: 0.9,
          feedback_text: 'Great answer.',
          tags_tested: [],
          created_at: '2026-01-01T00:02:00Z',
        });
      }
      if (method === 'POST' && path === '/api/learning/quizzes/session-1/advance') {
        current = { ...current, status: 'completed', completed_at: '2026-01-01T00:03:00Z' };
        return jsonResponse(current);
      }
      if (method === 'GET' && path === '/api/learning/quizzes/session-1/summary') {
        return jsonResponse({
          overall_score: 0.9,
          question_count: 1,
          answers: [],
          weakest_tag_ids: [],
        });
      }
      if (method === 'POST' && path === '/api/learning/quizzes/session-1/followup') {
        const body = (await request.clone().json()) as { content: string };
        expect(body.content).toBe('Why not a garbage collector?');
        return jsonResponse({
          id: 'followup-1',
          role: 'assistant',
          content: 'Because ownership tracks lifetimes at compile time.',
          created_at: '2026-01-01T00:02:30Z',
        });
      }
      throw new Error(`Unhandled request in test: ${method} ${path}`);
    }),
  );

  const user = userEvent.setup();
  await renderLearning(<SessionView kind="quiz" courseId="course-1" sessionId="session-1" />);

  expect(await screen.findByText(/borrow checker enforce/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /^start quiz$/i }));

  const answerBox = await screen.findByLabelText('Your answer');
  await user.type(answerBox, 'It enforces memory safety without a garbage collector.');
  await user.click(screen.getByRole('button', { name: /^submit$/i }));

  expect(await screen.findByText('90%')).toBeInTheDocument();
  expect(screen.getByText('Great answer.')).toBeInTheDocument();

  await user.type(
    screen.getByPlaceholderText(/ask a follow-up question/i),
    'Why not a garbage collector?',
  );
  await user.click(screen.getByRole('button', { name: /^ask$/i }));
  expect(
    await screen.findByText('Because ownership tracks lifetimes at compile time.'),
  ).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /^next$/i }));

  expect(await screen.findByRole('heading', { name: /quiz complete/i })).toBeInTheDocument();
  expect(screen.getByText('Score: 90%')).toBeInTheDocument();
});

function exerciseSession(overrides: Record<string, unknown> = {}) {
  return {
    id: 'session-2',
    path_item_id: 'item-1',
    status: 'completed',
    current_step_index: 0,
    created_at: '2026-01-01T00:00:00Z',
    started_at: '2026-01-01T00:01:00Z',
    completed_at: '2026-01-01T00:03:00Z',
    steps: [
      {
        id: 'step-1',
        order_index: 0,
        instruction_text: 'Write a function that borrows a vector.',
        hint_text: null,
        target_tag_ids: [],
        status: 'submitted',
      },
    ],
    ...overrides,
  };
}

it('renders an already-completed exercise summary with a pass rate', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch((method, path) => {
      if (method === 'GET' && path === '/api/learning/exercises/session-2') {
        return jsonResponse(exerciseSession());
      }
      if (method === 'GET' && path === '/api/learning/exercises/session-2/summary') {
        return jsonResponse({ pass_rate: 1, step_count: 1, submissions: [], weakest_tag_ids: [] });
      }
      throw new Error(`Unhandled request in test: ${method} ${path}`);
    }),
  );

  await renderLearning(<SessionView kind="exercise" courseId="course-1" sessionId="session-2" />);

  expect(await screen.findByRole('heading', { name: /exercise complete/i })).toBeInTheDocument();
  expect(await screen.findByText('Pass rate: 100%')).toBeInTheDocument();
});
