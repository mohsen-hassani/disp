import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type { CourseOut } from '../../../src/api/generated';
import { CourseList } from '../../../src/components/learning/CourseList';
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

function course(overrides: Partial<CourseOut> = {}): CourseOut {
  return {
    id: 'course-1',
    title: 'Intro to Rust',
    description: 'A beginner course',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

it('renders the list of courses', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch((method, path) => {
      if (method === 'GET' && path === '/api/learning/courses') {
        return jsonResponse({ items: [course()], next_cursor: null, has_more: false });
      }
      throw new Error(`Unhandled request in test: ${method} ${path}`);
    }),
  );

  await renderLearning(<CourseList />);

  expect(await screen.findByText('Intro to Rust')).toBeInTheDocument();
  expect(screen.getByText('A beginner course')).toBeInTheDocument();
  expect(screen.getByText('Active')).toBeInTheDocument();
});

it('shows the empty state and creates a course from it', async () => {
  let created = false;
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch(async (method, path, request) => {
      if (method === 'GET' && path === '/api/learning/courses') {
        return jsonResponse({
          items: created ? [course({ title: 'Rust Basics' })] : [],
          next_cursor: null,
          has_more: false,
        });
      }
      if (method === 'POST' && path === '/api/learning/courses') {
        const body = (await request.clone().json()) as { title: string };
        expect(body.title).toBe('Rust Basics');
        created = true;
        return jsonResponse(course({ title: 'Rust Basics' }), { status: 201 });
      }
      throw new Error(`Unhandled request in test: ${method} ${path}`);
    }),
  );

  const user = userEvent.setup();
  await renderLearning(<CourseList />);

  expect(await screen.findByText(/no courses yet/i)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /create your first course/i }));
  await user.type(screen.getByLabelText('Title'), 'Rust Basics');
  await user.click(screen.getByRole('button', { name: /^create course$/i }));

  expect(await screen.findByText('Rust Basics')).toBeInTheDocument();
});
