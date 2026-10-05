import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type { PathItemOut } from '../../../src/api/generated';
import { PathPage } from '../../../src/components/learning/PathPage';
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

function item(overrides: Partial<PathItemOut> = {}): PathItemOut {
  return {
    id: 'item-1',
    course_id: 'course-1',
    tier: 'concepts',
    order_index: 0,
    title: 'Ownership basics',
    est_minutes: 15,
    status: 'draft',
    completion_status: 'not_started',
    completed_at: null,
    topic_ids: [],
    ...overrides,
  };
}

it('renders draft path items grouped by tier and approves the path', async () => {
  let items = [item()];
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch(async (method, path, request) => {
      if (method === 'GET' && path === '/api/learning/courses/course-1/path') {
        return jsonResponse(items);
      }
      if (method === 'POST' && path === '/api/learning/courses/course-1/path/approve') {
        items = items.map((current) => ({ ...current, status: 'approved' }));
        return jsonResponse(items);
      }
      throw new Error(`Unhandled request in test: ${method} ${path} ${await request.text()}`);
    }),
  );

  const user = userEvent.setup();
  await renderLearning(<PathPage courseId="course-1" />);

  expect(await screen.findByText('Ownership basics')).toBeInTheDocument();
  expect(screen.getByText('Concepts')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /approve path/i }));

  expect(await screen.findByText('Path approved.')).toBeInTheDocument();
});

it('edits a draft item title and deletes another draft item', async () => {
  let items = [item(), item({ id: 'item-2', order_index: 1, title: 'Borrowing' })];
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch(async (method, path, request) => {
      if (method === 'GET' && path === '/api/learning/courses/course-1/path') {
        return jsonResponse(items);
      }
      if (method === 'PATCH' && path === '/api/learning/path-items/item-1') {
        const body = (await request.clone().json()) as { title?: string };
        items = items.map((current) =>
          current.id === 'item-1' ? { ...current, title: body.title ?? current.title } : current,
        );
        return jsonResponse(items[0]);
      }
      if (method === 'DELETE' && path === '/api/learning/path-items/item-2') {
        items = items.filter((current) => current.id !== 'item-2');
        return new Response(null, { status: 204 });
      }
      throw new Error(`Unhandled request in test: ${method} ${path}`);
    }),
  );

  const user = userEvent.setup();
  await renderLearning(<PathPage courseId="course-1" />);
  await screen.findByText('Ownership basics');

  await user.click(screen.getByText('Ownership basics'));
  const titleInput = screen.getByDisplayValue('Ownership basics');
  await user.clear(titleInput);
  await user.type(titleInput, 'Ownership fundamentals');
  await user.click(screen.getByRole('button', { name: /^save$/i }));

  expect(await screen.findByText('Ownership fundamentals')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /delete borrowing/i }));
  await vi.waitFor(() => expect(screen.queryByText('Borrowing')).not.toBeInTheDocument());
});

it('shows an empty state when there is no path yet', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch((method, path) => {
      if (method === 'GET' && path === '/api/learning/courses/course-1/path') {
        return jsonResponse([]);
      }
      throw new Error(`Unhandled request in test: ${method} ${path}`);
    }),
  );

  await renderLearning(<PathPage courseId="course-1" />);

  expect(await screen.findByText(/no path yet/i)).toBeInTheDocument();
});
