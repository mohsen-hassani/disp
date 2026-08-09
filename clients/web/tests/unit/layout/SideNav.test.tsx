import { screen } from '@testing-library/react';
import { LayoutDashboard, Settings, StickyNote } from 'lucide-react';
import { expect, it } from 'vitest';

import type { NavSection } from '../../../src/components/layout/navItems';
import { SideNav } from '../../../src/components/layout/SideNav';
import { renderNotes } from '../notes/testUtils';

const sections: NavSection[] = [
  {
    id: 'primary',
    label: null,
    items: [
      { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, path: '/', desktopOnly: false },
    ],
  },
  {
    id: 'modules',
    label: 'Modules',
    items: [{ id: 'notes', label: 'Notes', icon: StickyNote, path: '/notes', desktopOnly: false }],
  },
  {
    id: 'system',
    label: null,
    items: [
      { id: 'settings', label: 'Settings', icon: Settings, path: '/settings', desktopOnly: false },
    ],
  },
];

it('renders every item as a link with its label', async () => {
  await renderNotes(<SideNav sections={sections} />);

  expect(screen.getByRole('link', { name: /dashboard/i })).toHaveAttribute('href', '/');
  expect(screen.getByRole('link', { name: /notes/i })).toHaveAttribute('href', '/notes');
  expect(screen.getByRole('link', { name: /settings/i })).toHaveAttribute('href', '/settings');
});

it('labels the nav landmark "Main"', async () => {
  await renderNotes(<SideNav sections={sections} />);
  expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
});

it('renders a section heading only where the section has a label', async () => {
  await renderNotes(<SideNav sections={sections} />);

  expect(screen.getByRole('heading', { name: 'Modules' })).toBeInTheDocument();
  // The unlabelled sections still group their items, they just announce no
  // heading — one heading total, not three.
  expect(screen.getAllByRole('heading')).toHaveLength(1);
});

it('associates the Modules list with its heading for screen readers', async () => {
  await renderNotes(<SideNav sections={sections} />);

  const list = screen.getByRole('list', { name: 'Modules' });
  expect(list).toContainElement(screen.getByRole('link', { name: /notes/i }));
});
