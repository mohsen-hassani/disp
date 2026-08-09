import { LayoutDashboard, Settings, UserPlus, type LucideIcon } from 'lucide-react';

import type { ModuleManifestOut } from '../../api/generated';
import { resolveIcon } from '../../lib/icons';
import { MODULE_SCREENS, moduleBasePath } from '../../modules/registry';

export interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
  path: string;
  /** SideNav only (desktop) — never rendered in BottomNav, per §12.2's table. */
  desktopOnly: boolean;
}

export interface NavSection {
  id: string;
  /** `null` renders the items with no heading — grouping without a label. */
  label: string | null;
  items: NavItem[];
}

/**
 * Pure function (no hooks) so SideNav and BottomNav can share one computed
 * list without either of them risking a different manifest/auth snapshot —
 * the milestone's own resolved "open question" on this exact risk.
 *
 * WEB-SPEC §12.2: module entries come from each manifest's `client_nav`
 * (label, icon, order — all server-controlled) filtered by `MODULE_SCREENS`
 * (does this client actually have the screens). A module declaring
 * `client_nav` that this client can't render is skipped silently: it still
 * appears on the dashboard, just never in navigation.
 */
export function computeNavSections(params: {
  modules: readonly ModuleManifestOut[];
  isAdmin: boolean;
  /** Injectable so ordering and filtering can be tested independently of
   *  which domains this client happens to ship screens for today. */
  screens?: ReadonlySet<string>;
}): NavSection[] {
  const { modules, isAdmin, screens = MODULE_SCREENS } = params;

  const moduleItems: NavItem[] = modules
    .filter((module) => module.client_nav != null && screens.has(module.domain))
    .sort(
      (a, b) =>
        (a.client_nav?.order ?? 100) - (b.client_nav?.order ?? 100) ||
        a.domain.localeCompare(b.domain),
    )
    .map((module) => ({
      id: module.domain,
      label: module.client_nav?.label ?? module.name,
      icon: resolveIcon(module.client_nav?.icon),
      path: moduleBasePath(module.domain),
      desktopOnly: false,
    }));

  const systemItems: NavItem[] = [
    { id: 'settings', label: 'Settings', icon: Settings, path: '/settings', desktopOnly: false },
  ];
  if (isAdmin) {
    systemItems.push({
      id: 'admin-invites',
      label: 'Invitations',
      icon: UserPlus,
      path: '/admin/invites',
      desktopOnly: true,
    });
  }

  const sections: NavSection[] = [
    {
      id: 'primary',
      label: null,
      items: [
        {
          id: 'dashboard',
          label: 'Dashboard',
          icon: LayoutDashboard,
          path: '/',
          desktopOnly: false,
        },
      ],
    },
  ];

  // Omitted entirely when empty — a "Modules" heading with nothing under it
  // would advertise a capability this install doesn't have.
  if (moduleItems.length > 0) {
    sections.push({ id: 'modules', label: 'Modules', items: moduleItems });
  }

  sections.push({ id: 'system', label: null, items: systemItems });
  return sections;
}

/** Section grouping is a desktop affordance; BottomNav wants the flat list. */
export function flattenNavSections(sections: readonly NavSection[]): NavItem[] {
  return sections.flatMap((section) => section.items);
}
