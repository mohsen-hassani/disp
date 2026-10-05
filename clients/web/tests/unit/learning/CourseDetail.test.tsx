import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type {
  CourseOut,
  JobOut,
  ProgressOut,
  SourceOut,
  WeakPointOut,
} from '../../../src/api/generated';
import { CourseDetailPage } from '../../../src/components/learning/CourseDetail';
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
    status: 'draft',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function source(overrides: Partial<SourceOut> = {}): SourceOut {
  return {
    id: 'source-1',
    course_id: 'course-1',
    title: 'Chapter 1',
    content_type: 'markdown',
    token_count: 500,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function progress(overrides: Partial<ProgressOut> = {}): ProgressOut {
  return { completed: 2, total: 5, by_tier: {}, ...overrides };
}

function job(overrides: Partial<JobOut> = {}): JobOut {
  return {
    id: 'job-1',
    course_id: 'course-1',
    kind: 'index',
    status: 'succeeded',
    phase: null,
    progress_current: 1,
    progress_total: 1,
    error_code: null,
    created_at: '2026-01-01T00:00:00Z',
    started_at: '2026-01-01T00:00:00Z',
    finished_at: '2026-01-01T00:00:01Z',
    ...overrides,
  };
}

function baseHandler(overrides: { courseStatus?: string; sources?: SourceOut[] } = {}) {
  const weakPoints: WeakPointOut[] = [];
  return (method: string, path: string): Response | undefined => {
    if (method === 'GET' && path === '/api/learning/courses/course-1') {
      return jsonResponse(course({ status: overrides.courseStatus ?? 'draft' }));
    }
    if (method === 'GET' && path === '/api/learning/courses/course-1/sources') {
      return jsonResponse(overrides.sources ?? [source()]);
    }
    if (method === 'GET' && path === '/api/learning/courses/course-1/progress') {
      return jsonResponse(progress());
    }
    if (method === 'GET' && path === '/api/learning/courses/course-1/weak-points') {
      return jsonResponse(weakPoints);
    }
    return undefined;
  };
}

it('renders the course, its sources, and progress', async () => {
  const handler = baseHandler();
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch((method, path) => {
      const response = handler(method, path);
      if (!response) throw new Error(`Unhandled request in test: ${method} ${path}`);
      return response;
    }),
  );
  await renderLearning(<CourseDetailPage courseId="course-1" />);

  expect(await screen.findByRole('heading', { name: 'Intro to Rust' })).toBeInTheDocument();
  expect(screen.getByText('Chapter 1')).toBeInTheDocument();
  expect(screen.getByText('2 / 5 lessons completed')).toBeInTheDocument();
});

it('starts indexing when there are sources', async () => {
  const handler = baseHandler();
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch(async (method, path) => {
      if (method === 'POST' && path === '/api/learning/courses/course-1/index') {
        return jsonResponse(job({ status: 'running' }), { status: 202 });
      }
      if (method === 'GET' && path === '/api/learning/jobs/job-1') {
        return jsonResponse(job({ status: 'succeeded' }));
      }
      const response = handler(method, path);
      if (!response) throw new Error(`Unhandled request in test: ${method} ${path}`);
      return response;
    }),
  );

  const user = userEvent.setup();
  await renderLearning(<CourseDetailPage courseId="course-1" />);

  await screen.findByRole('heading', { name: 'Intro to Rust' });
  await user.click(screen.getByRole('button', { name: /index course/i }));

  expect(await screen.findByText('Indexing started.')).toBeInTheDocument();
});

it('surfaces a toast when the index job settles as failed (e.g. DISP_LLM_ENABLED=false)', async () => {
  const handler = baseHandler();
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch((method, path) => {
      if (method === 'POST' && path === '/api/learning/courses/course-1/index') {
        return jsonResponse(job({ status: 'running' }), { status: 202 });
      }
      if (method === 'GET' && path === '/api/learning/jobs/job-1') {
        return jsonResponse(
          job({ status: 'failed', error_code: 'modules.learning.llm_unavailable' }),
        );
      }
      const response = handler(method, path);
      if (!response) throw new Error(`Unhandled request in test: ${method} ${path}`);
      return response;
    }),
  );

  const user = userEvent.setup();
  await renderLearning(<CourseDetailPage courseId="course-1" />);

  await screen.findByRole('heading', { name: 'Intro to Rust' });
  await user.click(screen.getByRole('button', { name: /index course/i }));

  expect(
    await screen.findByText('AI features are temporarily unavailable. Try again shortly.'),
  ).toBeInTheDocument();
});

it('adds a source, removes it, and offers path generation once active', async () => {
  let sources = [source()];
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch(async (method, path, request) => {
      if (method === 'GET' && path === '/api/learning/courses/course-1') {
        return jsonResponse(course({ status: 'active' }));
      }
      if (method === 'GET' && path === '/api/learning/courses/course-1/sources') {
        return jsonResponse(sources);
      }
      if (method === 'GET' && path === '/api/learning/courses/course-1/progress') {
        return jsonResponse(progress());
      }
      if (method === 'GET' && path === '/api/learning/courses/course-1/weak-points') {
        return jsonResponse([]);
      }
      if (method === 'POST' && path === '/api/learning/courses/course-1/sources') {
        const body = await request.clone().formData();
        sources = [...sources, source({ id: 'source-2', title: String(body.get('title')) })];
        return jsonResponse(sources[1], { status: 201 });
      }
      if (method === 'DELETE' && path === '/api/learning/sources/source-1') {
        sources = sources.filter((s) => s.id !== 'source-1');
        return new Response(null, { status: 204 });
      }
      if (method === 'POST' && path === '/api/learning/courses/course-1/path/generate') {
        return jsonResponse(job({ status: 'running' }), { status: 202 });
      }
      throw new Error(`Unhandled request in test: ${method} ${path}`);
    }),
  );

  const user = userEvent.setup();
  await renderLearning(<CourseDetailPage courseId="course-1" />);
  await screen.findByRole('heading', { name: 'Intro to Rust' });

  await user.click(screen.getByRole('button', { name: /^add source$/i }));
  await user.type(screen.getByLabelText('Title'), 'Chapter 2');
  await user.type(screen.getByLabelText('Content'), 'Some raw notes.');
  await user.click(screen.getByRole('button', { name: /^add source$/i }));

  expect(await screen.findByText('Chapter 2')).toBeInTheDocument();

  const removeButtons = screen.getAllByRole('button', { name: /^remove$/i });
  await user.click(removeButtons[0]);
  await screen.findByText('Chapter 2');

  await user.click(screen.getByRole('button', { name: /generate path/i }));
  expect(await screen.findByText('Generating a learning path…')).toBeInTheDocument();
});
