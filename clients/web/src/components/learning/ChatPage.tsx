import { useQuery } from '@tanstack/react-query';
import { MessageSquare, Plus, Send } from 'lucide-react';
import { type FormEvent, type ReactElement, useState } from 'react';

import { learningChatMessagesQueryOptions, learningChatsQueryOptions } from '../../api/queries';
import { EmptyState } from '../feedback/EmptyState';
import { useToast } from '../feedback/ToastProvider';
import { describeLearningError, useCreateChat, useSendChatMessage } from './useLearningMutations';

const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

interface ChatPageProps {
  courseId: string;
}

function ChatThread({ chatId }: { chatId: string }): ReactElement {
  const [content, setContent] = useState('');
  const { showToast } = useToast();
  const messagesQuery = useQuery(learningChatMessagesQueryOptions(chatId));
  const sendMessage = useSendChatMessage();
  const messages = messagesQuery.data ?? [];

  function handleSend(event: FormEvent): void {
    event.preventDefault();
    const text = content;
    setContent('');
    sendMessage.mutate(
      { chatId, content: text },
      { onError: (error) => showToast(describeLearningError(error), 'error') },
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      <div className="mb-3 flex flex-1 flex-col gap-2 overflow-y-auto">
        {messagesQuery.isPending && <p aria-busy="true">Loading…</p>}
        {messages.map((message) => (
          <div
            key={message.id}
            className={`max-w-[80%] rounded-md border p-3 text-sm ${
              message.role === 'user'
                ? 'border-border bg-surface self-end'
                : 'border-border bg-surface-sunken self-start'
            }`}
          >
            {message.content}
          </div>
        ))}
      </div>
      <form onSubmit={handleSend} className="flex gap-2">
        <input
          type="text"
          required
          placeholder="Ask about this course…"
          value={content}
          onChange={(event) => setContent(event.target.value)}
          className="border-border bg-surface min-w-0 flex-1 rounded-sm border px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={sendMessage.isPending}
          className={`${primaryButtonClass} inline-flex items-center gap-1.5`}
        >
          <Send className="h-4 w-4" aria-hidden="true" />
          Send
        </button>
      </form>
    </div>
  );
}

/** M20 §23: `/learning/$courseId/chat` — course-wide freeform chat (§13.3's retrieval). */
export function ChatPage({ courseId }: ChatPageProps): ReactElement {
  const { showToast } = useToast();
  const chatsQuery = useQuery(learningChatsQueryOptions(courseId));
  const createChat = useCreateChat();
  const [activeChatId, setActiveChatId] = useState<string | undefined>(undefined);

  const chats = chatsQuery.data ?? [];
  const selectedChatId = activeChatId ?? chats[0]?.id;

  function handleNewChat(): void {
    createChat.mutate(
      { courseId, payload: { scope_type: 'freeform' } },
      {
        onSuccess: (chat) => setActiveChatId(chat.id),
        onError: (error) => showToast(describeLearningError(error), 'error'),
      },
    );
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      <div className="mb-4 flex items-center justify-between">
        <h1>Chat</h1>
        <button
          type="button"
          onClick={handleNewChat}
          disabled={createChat.isPending}
          className={`${secondaryButtonClass} inline-flex items-center gap-1.5`}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          New chat
        </button>
      </div>

      {chatsQuery.isSuccess && chats.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {chats.map((chat) => (
            <button
              key={chat.id}
              type="button"
              onClick={() => setActiveChatId(chat.id)}
              className={
                chat.id === selectedChatId
                  ? `${secondaryButtonClass} bg-surface-sunken`
                  : secondaryButtonClass
              }
            >
              {chat.title ?? chat.scope_type}
            </button>
          ))}
        </div>
      )}

      {chatsQuery.isSuccess && chats.length === 0 && (
        <EmptyState
          icon={MessageSquare}
          title="No chats yet. Start one to ask questions about this course."
          action={
            <button type="button" onClick={handleNewChat} className={primaryButtonClass}>
              Start a chat
            </button>
          }
        />
      )}

      {selectedChatId && <ChatThread chatId={selectedChatId} />}
    </div>
  );
}
