import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LayoutDashboard, Settings, StickyNote, UserPlus } from 'lucide-react';
import { expect, it } from 'vitest';

import type { NavItem, NavSection } from '../../../src/components/layout/navItems';
import { BottomNav } from '../../../src/components/layout/BottomNav';
import { renderNotes } from '../notes/testUtils';

function item(overrides: Partial<NavItem>): NavItem {
  return {
    id: 'x',
    label: 'X',
    icon: LayoutDashboard,
    path: '/x',
    desktopOnly: false,
    ...overrides,
  };
}

// BottomNav flattens sections back to one list, so how the items are grouped
// is irrelevant here — one section carries them all.
function sectionsOf(items: NavItem[]): NavSection[] {
  return [{ id: 'primary', label: null, items }];
}

it('excludes desktopOnly items and renders the rest as links', async () => {
  const items: NavItem[] = [
    item({ id: 'dashboard', label: 'Dashboard', path: '/' }),
    item({ id: 'notes', label: 'Notes', icon: StickyNote, path: '/notes' }),
    item({ id: 'admin-invites', label: 'Invitations', icon: UserPlus, desktopOnly: true }),
  ];
  await renderNotes(<BottomNav sections={sectionsOf(items)} />);

  expect(screen.getByRole('link', { name: /dashboard/i })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /notes/i })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /invitations/i })).not.toBeInTheDocument();
});

// §12.3: more than MAX_SLOTS mobile-visible items collapses the overflow
// into a "More" sheet rather than rendering a 5th tab.
it('collapses items past the 4-slot cap into a More sheet', async () => {
  const items: NavItem[] = [
    item({ id: 'a', label: 'A', path: '/a' }),
    item({ id: 'b', label: 'B', path: '/b' }),
    item({ id: 'c', label: 'C', path: '/c' }),
    item({ id: 'd', label: 'D', path: '/d' }),
    item({ id: 'e', label: 'E', icon: Settings, path: '/e' }),
  ];
  const user = userEvent.setup();
  await renderNotes(<BottomNav sections={sectionsOf(items)} />);

  expect(screen.getAllByRole('link')).toHaveLength(3);
  expect(screen.queryByRole('link', { name: 'D' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'E' })).not.toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /more/i }));
  const dialog = await screen.findByRole('dialog');
  expect(dialog).toHaveTextContent('D');
  expect(dialog).toHaveTextContent('E');
});
