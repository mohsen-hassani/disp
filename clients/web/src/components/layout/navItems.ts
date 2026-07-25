import { LayoutDashboard, StickyNote, Settings, UserPlus, type LucideIcon } from 'lucide-react';

/**
 * WEB-SPEC §12.2: a module registering tiles/settings but with no bespoke
 * screen appears only on the dashboard, never in navigation — bespoke
 * screens require bespoke code, and the client must not pretend a module
 * has a screen it doesn't. v1 has exactly one entry. Adding a future
 * module's screen is a one-line addition here plus the screen itself.
 */
export const MODULE_ROUTES: Record<string, { path: string; label: string; icon: LucideIcon }> = {
  notes: { path: '/notes', label: 'Notes', icon: StickyNote },
};

export interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
  path: string;
  /** SideNav only (desktop) — never rendered in BottomNav, per §12.2's table. */
  desktopOnly: boolean;
}

/**
 * Pure function (no hooks) so SideNav and BottomNav can share one computed
 * list without either of them risking a different manifest/auth snapshot —
 * the milestone's own resolved "open question" on this exact risk.
 */
export function computeNavItems(params: {
  manifestDomains: readonly string[];
  isAdmin: boolean;
}): NavItem[] {
  const { manifestDomains, isAdmin } = params;
  const items: NavItem[] = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, path: '/', desktopOnly: false },
  ];

  for (const domain of manifestDomains) {
    const route = MODULE_ROUTES[domain];
    if (route) {
      items.push({
        id: domain,
        label: route.label,
        icon: route.icon,
        path: route.path,
        desktopOnly: false,
      });
    }
  }

  items.push({
    id: 'settings',
    label: 'Settings',
    icon: Settings,
    path: '/settings',
    desktopOnly: false,
  });

  if (isAdmin) {
    items.push({
      id: 'admin-invites',
      label: 'Invitations',
      icon: UserPlus,
      path: '/admin/invites',
      desktopOnly: true,
    });
  }

  return items;
}
