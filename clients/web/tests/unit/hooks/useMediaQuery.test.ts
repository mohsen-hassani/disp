import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { useMediaQuery } from '../../../src/hooks/useMediaQuery';

afterEach(() => {
  vi.restoreAllMocks();
});

function fakeMql(initialMatches: boolean) {
  let matches = initialMatches;
  let changeListener: (() => void) | undefined;
  const mql = {
    get matches() {
      return matches;
    },
    addEventListener: (_event: string, listener: () => void) => {
      changeListener = listener;
    },
    removeEventListener: () => {
      changeListener = undefined;
    },
  } as unknown as MediaQueryList;
  return {
    mql,
    set: (next: boolean) => {
      matches = next;
      changeListener?.();
    },
  };
}

it('reflects the current match state and updates on a change event', () => {
  const { mql, set } = fakeMql(false);
  vi.spyOn(window, 'matchMedia').mockReturnValue(mql);

  const { result } = renderHook(() => useMediaQuery('(min-width: 768px)'));
  expect(result.current).toBe(false);

  act(() => set(true));
  expect(result.current).toBe(true);
});

it('unsubscribes on unmount', () => {
  const { mql } = fakeMql(false);
  const removeSpy = vi.fn();
  vi.spyOn(window, 'matchMedia').mockReturnValue({
    ...mql,
    removeEventListener: removeSpy,
  } as unknown as MediaQueryList);

  const { unmount } = renderHook(() => useMediaQuery('(min-width: 768px)'));
  unmount();
  expect(removeSpy).toHaveBeenCalled();
});
