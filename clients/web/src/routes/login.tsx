import { createFileRoute, redirect } from '@tanstack/react-router';

import { getAuthState } from '../auth/authState';
import { isAuthenticated } from '../auth/guards';
import { LoginPage } from './-login';

// WEB-SPEC §9: `/login` is anonymous-only — an already-authenticated user
// hitting it (back button, a stale bookmark) is bounced to `/`, not shown a
// login form for a session they already have.
export const Route = createFileRoute('/login')({
  validateSearch: (search: Record<string, unknown>): { next?: string } => ({
    next: typeof search.next === 'string' ? search.next : undefined,
  }),
  beforeLoad: () => {
    if (isAuthenticated(getAuthState())) {
      throw redirect({ to: '/' });
    }
  },
  component: LoginPage,
  staticData: { title: 'Sign in · DISP' },
});
