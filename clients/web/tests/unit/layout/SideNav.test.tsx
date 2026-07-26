import { screen } from '@testing-library/react';
import { LayoutDashboard, Settings } from 'lucide-react';
import { expect, it } from 'vitest';

import type { NavItem } from '../../../src/components/layout/navItems';
import { SideNav } from '../../../src/components/layout/SideNav';
import { renderNotes } from '../notes/testUtils';

const items: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, path: '/', desktopOnly: false },
  { id: 'settings', label: 'Settings', icon: Settings, path: '/settings', desktopOnly: false },
];

it('renders every item as a link with its label', async () => {
  await renderNotes(<SideNav items={items} />);

  expect(screen.getByRole('link', { name: /dashboard/i })).toHaveAttribute('href', '/');
  expect(screen.getByRole('link', { name: /settings/i })).toHaveAttribute('href', '/settings');
});

it('labels the nav landmark "Main"', async () => {
  await renderNotes(<SideNav items={items} />);
  expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
});
