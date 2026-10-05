import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type { PathItemContentOut, QuizSessionOut } from '../../../src/api/generated';
import { PathItemPage } from '../../../src/components/learning/PathItemPage';
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

function content(): PathItemContentOut {
  return {
    path_item: {
      id: 'item-1',
      course_id: 'course-1',
      tier: 'concepts',
      order_index: 0,
      title: 'Ownership basics',
      est_minutes: 15,
      status: 'approved',
      completion_status: 'not_started',
      completed_at: null,
      topic_ids: [],
    },
    sections: [
      {
        id: 'section-1',
        heading_path: 'Ch1 > Ownership',
        content_text: 'Ownership is core to Rust.',
      },
    ],
  };
}

function quizSession(): QuizSessionOut {
  return {
    id: 'session-1',
    path_item_id: 'item-1',
    status: 'draft',
    current_question_index: 0,
    created_at: '2026-01-01T00:00:00Z',
    started_at: null,
    completed_at: null,
    questions: [],
  };
}

it('renders lesson content and explains it on request', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch(async (method, path) => {
      if (method === 'GET' && path === '/api/learning/path-items/item-1/content') {
        return jsonResponse(content());
      }
      if (method === 'POST' && path === '/api/learning/path-items/item-1/explain') {
        return jsonResponse({ content: 'Here is a simpler explanation.' });
      }
      throw new Error(`Unhandled request in test: ${method} ${path}`);
    }),
  );

  const user = userEvent.setup();
  await renderLearning(<PathItemPage courseId="course-1" itemId="item-1" />);

  expect(await screen.findByRole('heading', { name: 'Ownership basics' })).toBeInTheDocument();
  expect(screen.getByText('Ownership is core to Rust.')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /explain differently/i }));

  expect(await screen.findByText('Here is a simpler explanation.')).toBeInTheDocument();
});

it('starts a quiz session and navigates to it', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch(async (method, path) => {
      if (method === 'GET' && path === '/api/learning/path-items/item-1/content') {
        return jsonResponse(content());
      }
      if (method === 'POST' && path === '/api/learning/path-items/item-1/quizzes') {
        return jsonResponse(quizSession(), { status: 201 });
      }
      if (method === 'GET' && path === '/api/learning/quizzes/session-1') {
        return jsonResponse(quizSession());
      }
      throw new Error(`Unhandled request in test: ${method} ${path}`);
    }),
  );

  const user = userEvent.setup();
  const { router } = await renderLearning(<PathItemPage courseId="course-1" itemId="item-1" />);

  await screen.findByRole('heading', { name: 'Ownership basics' });
  await user.click(screen.getByRole('button', { name: /start quiz/i }));

  await vi.waitFor(() =>
    expect(router.state.location.pathname).toBe('/learning/course-1/quiz/session-1'),
  );
});
