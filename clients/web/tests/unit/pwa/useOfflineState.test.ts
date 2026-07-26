import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { useOfflineState } from '../../../src/hooks/useOfflineState';
import { setOnline } from './testUtils';

const POLL_INTERVAL_MS = 30_000;

let fetchSpy: ReturnType<typeof vi.spyOn>;
let setIntervalSpy: ReturnType<typeof vi.spyOn> | undefined;

beforeEach(() => {
  setOnline(true);
});

afterEach(() => {
  fetchSpy?.mockRestore();
  setIntervalSpy?.mockRestore();
  setOnline(true);
});

it('reflects the browser online/offline events', () => {
  const { result } = renderHook(() => useOfflineState());
  expect(result.current).toBe(false);

  setOnline(false);
  expect(result.current).toBe(true);

  setOnline(true);
  expect(result.current).toBe(false);
});

// Case 42/43's data half, and the milestone's own resolved open question
// (poll paused while hidden): driving the interval's own callback directly
// rather than advancing vitest's fake clock 30s — combining `vi.useFakeTimers()`
// with React's `act()`-flushed state updates deadlocks jsdom's environment
// here (React's scheduler falls back to a `setTimeout`-based macrotask
// jsdom has no `MessageChannel` to avoid, and advancing the fake clock
// never resolves it). Asserting the registered interval's delay plus
// invoking its callback directly exercises the same production code path
// without that interaction.
it('polls /health/live every 30s while offline, clearing once it succeeds', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 200 }));
  setIntervalSpy = vi.spyOn(window, 'setInterval');
  setOnline(false);
  const { result } = renderHook(() => useOfflineState());
  expect(result.current).toBe(true);

  expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), POLL_INTERVAL_MS);
  const pollCallback = setIntervalSpy.mock.calls[0]?.[0] as () => void;

  await act(async () => {
    pollCallback();
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(fetchSpy).toHaveBeenCalledWith('/health/live', { method: 'HEAD', cache: 'no-store' });
  await waitFor(() => expect(result.current).toBe(false));
});

it('does not poll while the tab is hidden', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 200 }));
  setIntervalSpy = vi.spyOn(window, 'setInterval');
  Object.defineProperty(document, 'hidden', { value: true, configurable: true });
  setOnline(false);
  renderHook(() => useOfflineState());

  const pollCallback = setIntervalSpy.mock.calls[0]?.[0] as () => void;
  await act(async () => {
    pollCallback();
    await Promise.resolve();
  });

  expect(fetchSpy).not.toHaveBeenCalled();
  Object.defineProperty(document, 'hidden', { value: false, configurable: true });
});
