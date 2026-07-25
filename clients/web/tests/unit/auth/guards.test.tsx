import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';

import { ForbiddenScreen, isAdmin, isAuthenticated } from '../../../src/auth/guards';
import { TEST_USER } from './testUtils';

it('isAuthenticated/isAdmin narrow correctly on each state', () => {
  expect(isAuthenticated({ status: 'anonymous' })).toBe(false);
  expect(isAuthenticated({ status: 'authenticated', user: TEST_USER })).toBe(true);
  expect(isAdmin({ status: 'authenticated', user: TEST_USER })).toBe(false);
  expect(isAdmin({ status: 'authenticated', user: { ...TEST_USER, is_admin: true } })).toBe(true);
  expect(isAdmin({ status: 'anonymous' })).toBe(false);
});

it('ForbiddenScreen renders a 403 alert', () => {
  render(<ForbiddenScreen />);
  expect(screen.getByRole('alert')).toHaveTextContent(/forbidden/i);
});
