import { Link } from '@tanstack/react-router';
import type { ReactElement } from 'react';

import type { NavItem } from './navItems';

interface SideNavProps {
  items: NavItem[];
}

// md+ only (WEB-SPEC §12.1) — hidden via CSS (display:none), which also
// removes it from the tab order, so BottomNav's mobile-only items don't
// double up in keyboard traversal at desktop widths and vice versa.
export function SideNav({ items }: SideNavProps): ReactElement {
  return (
    <nav
      aria-label="Main"
      className="border-border hidden w-56 shrink-0 flex-col gap-1 border-r p-3 pl-[calc(0.75rem+env(safe-area-inset-left))] md:flex"
    >
      {items.map((item) => (
        <Link
          key={item.id}
          to={item.path}
          activeOptions={{ exact: item.path === '/' }}
          className="text-text-muted [&.active]:bg-surface-sunken [&.active]:text-text focus-visible:outline-accent flex items-center gap-3 rounded-md px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 [&.active]:font-medium"
          activeProps={{ className: 'active', 'aria-current': 'page' }}
        >
          <item.icon className="h-5 w-5 shrink-0 [.active_&]:fill-current" aria-hidden="true" />
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
