import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import type { ChatMessageOut, ChatSessionOut } from '../../../src/api/generated';
import { ChatPage } from '../../../src/components/learning/ChatPage';
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

function chatSession(overrides: Partial<ChatSessionOut> = {}): ChatSessionOut {
  return {
    id: 'chat-1',
    course_id: 'course-1',
    scope_type: 'freeform',
    title: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function message(overrides: Partial<ChatMessageOut> = {}): ChatMessageOut {
  return {
    id: 'message-1',
    role: 'assistant',
    content: 'Ask me anything about this course.',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

it('shows the empty state, starts a chat, and sends a message', async () => {
  let chats: ChatSessionOut[] = [];
  let messages: ChatMessageOut[] = [];
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    routedFetch(async (method, path, request) => {
      if (method === 'GET' && path === '/api/learning/courses/course-1/chats') {
        return jsonResponse(chats);
      }
      if (method === 'POST' && path === '/api/learning/courses/course-1/chats') {
        chats = [chatSession()];
        messages = [message()];
        return jsonResponse(chatSession(), { status: 201 });
      }
      if (method === 'GET' && path === '/api/learning/chats/chat-1/messages') {
        return jsonResponse(messages);
      }
      if (method === 'POST' && path === '/api/learning/chats/chat-1/messages') {
        const body = (await request.clone().json()) as { content: string };
        const userMessage = message({ id: 'message-2', role: 'user', content: body.content });
        const reply = message({ id: 'message-3', content: 'Ownership means one owner at a time.' });
        messages = [...messages, userMessage, reply];
        return jsonResponse(reply, { status: 201 });
      }
      throw new Error(`Unhandled request in test: ${method} ${path}`);
    }),
  );

  const user = userEvent.setup();
  await renderLearning(<ChatPage courseId="course-1" />);

  expect(await screen.findByText(/no chats yet/i)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /start a chat/i }));

  expect(await screen.findByText('Ask me anything about this course.')).toBeInTheDocument();

  await user.type(screen.getByPlaceholderText(/ask about this course/i), 'What is ownership?');
  await user.click(screen.getByRole('button', { name: /^send$/i }));

  expect(await screen.findByText('Ownership means one owner at a time.')).toBeInTheDocument();
});
