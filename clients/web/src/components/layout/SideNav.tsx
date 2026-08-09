import { Link } from '@tanstack/react-router';
import { type ReactElement, useId } from 'react';

import type { NavSection } from './navItems';

interface SideNavProps {
  sections: NavSection[];
}

// md+ only (WEB-SPEC §12.1) — hidden via CSS (display:none), which also
// removes it from the tab order, so BottomNav's mobile-only items don't
// double up in keyboard traversal at desktop widths and vice versa.
export function SideNav({ sections }: SideNavProps): ReactElement {
  return (
    <nav
      aria-label="Main"
      className="border-border hidden w-56 shrink-0 flex-col gap-4 border-r p-3 pl-[calc(0.75rem+env(safe-area-inset-left))] md:flex"
    >
      {sections.map((section) => (
        <SideNavSection key={section.id} section={section} />
      ))}
    </nav>
  );
}

// Each section is its own labelled group so a screen reader announces "Modules,
// list, 2 items" rather than one undifferentiated run of links. An unlabelled
// section still gets its own <ul> — the grouping is real either way, it just
// has no heading to announce.
function SideNavSection({ section }: { section: NavSection }): ReactElement {
  const headingId = useId();

  return (
    <div className="flex flex-col gap-1">
      {section.label && (
        <h2
          id={headingId}
          className="text-text-muted px-3 pt-1 pb-0.5 text-xs font-medium tracking-wide uppercase"
        >
          {section.label}
        </h2>
      )}
      <ul className="flex flex-col gap-1" aria-labelledby={section.label ? headingId : undefined}>
        {section.items.map((item) => (
          <li key={item.id}>
            <Link
              to={item.path}
              activeOptions={{ exact: item.path === '/' }}
              className="text-text-muted [&.active]:bg-surface-sunken [&.active]:text-text focus-visible:outline-accent flex items-center gap-3 rounded-md px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 [&.active]:font-medium"
              activeProps={{ className: 'active', 'aria-current': 'page' }}
            >
              <item.icon className="h-5 w-5 shrink-0 [.active_&]:fill-current" aria-hidden="true" />
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
