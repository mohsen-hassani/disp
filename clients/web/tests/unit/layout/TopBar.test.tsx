import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it } from 'vitest';

import { TopBar } from '../../../src/components/layout/TopBar';
import { setAuthState } from '../../../src/auth/authState';
import { setThemePreference } from '../../../src/lib/theme';
import { TEST_USER } from '../auth/testUtils';
import { renderNotes } from '../notes/testUtils';

afterEach(() => {
  setAuthState({ status: 'anonymous' });
  setThemePreference('system');
});

it('renders the DISP wordmark and falls back to the DISP page title', async () => {
  setAuthState({ status: 'anonymous' });
  await renderNotes(<TopBar />);

  expect(screen.getByRole('link', { name: 'DISP' })).toHaveAttribute('href', '/');
  expect(screen.getByRole('heading', { name: 'DISP' })).toBeInTheDocument();
});

it('hides the account menu while anonymous', async () => {
  setAuthState({ status: 'anonymous' });
  await renderNotes(<TopBar />);
  expect(screen.queryByRole('button', { name: TEST_USER.display_name })).not.toBeInTheDocument();
});

it('shows the account menu with name/email and the theme submenu options once authenticated', async () => {
  setAuthState({ status: 'authenticated', user: TEST_USER });
  const user = userEvent.setup();
  await renderNotes(<TopBar />);

  await user.click(screen.getByRole('button', { name: new RegExp(TEST_USER.display_name) }));
  expect(screen.getByText(TEST_USER.email)).toBeInTheDocument();

  // The submenu shows the current preference and every option (§12.4); the
  // click-through itself is Radix's own onSelect plumbing over
  // `setThemePreference`, already covered directly by theme.test.ts.
  await user.hover(screen.getByText('Theme'));
  expect(await screen.findByRole('menuitem', { name: /^dark/i })).toBeInTheDocument();
  expect(screen.getByRole('menuitem', { name: /^light/i })).toBeInTheDocument();
  expect(screen.getByRole('menuitem', { name: /^system/i })).toBeInTheDocument();
});
