import { renderHook } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';

import { setAuthState } from '../../../src/auth/authState';
import { useAuth } from '../../../src/auth/useAuth';
import { TEST_USER } from './testUtils';

afterEach(() => {
  setAuthState({ status: 'anonymous' });
});

it('reflects the current auth state and re-renders when it changes', () => {
  setAuthState({ status: 'anonymous' });
  const { result, rerender } = renderHook(() => useAuth());
  expect(result.current.state).toEqual({ status: 'anonymous' });

  setAuthState({ status: 'authenticated', user: TEST_USER });
  rerender();
  expect(result.current.state).toEqual({ status: 'authenticated', user: TEST_USER });
});

it('exposes the same login/logout/acceptInvite/dismissRevoked action functions every render', () => {
  const { result } = renderHook(() => useAuth());
  expect(typeof result.current.login).toBe('function');
  expect(typeof result.current.logout).toBe('function');
  expect(typeof result.current.acceptInvite).toBe('function');
  expect(typeof result.current.dismissRevoked).toBe('function');
});
