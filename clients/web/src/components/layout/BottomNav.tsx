import * as Dialog from '@radix-ui/react-dialog';
import { Link } from '@tanstack/react-router';
import { Ellipsis, X } from 'lucide-react';
import { type ReactElement, useId, useState } from 'react';

import { flattenNavSections, type NavItem, type NavSection } from './navItems';

interface BottomNavProps {
  sections: NavSection[];
}

// §12.3: max 4 slots. `desktopOnly` items (Invitations) never appear here at
// all. With Dashboard + Settings fixed, two modules with screens land exactly
// on 4; a third is what finally trips the "5th item collapses into More" rule
// below — which is now reachable through the manifest, not just theoretical.
const MAX_SLOTS = 4;

const linkClass =
  'text-text-muted [&.active]:text-text focus-visible:outline-accent flex min-h-14 min-w-16 flex-1 flex-col items-center justify-center gap-1 rounded-md text-xs focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 [&.active]:font-medium';

export function BottomNav({ sections }: BottomNavProps): ReactElement {
  // Section grouping is a desktop affordance (SideNav's headings); on mobile
  // the 4-slot bar has no room for headings, so flatten back to one list and
  // let §12.3's overflow rule below do its job unchanged.
  const mobileItems = flattenNavSections(sections).filter((item) => !item.desktopOnly);
  const overflowing = mobileItems.length > MAX_SLOTS;
  const visible = overflowing ? mobileItems.slice(0, MAX_SLOTS - 1) : mobileItems;
  const overflow = overflowing ? mobileItems.slice(MAX_SLOTS - 1) : [];

  return (
    <nav
      aria-label="Main"
      className="border-border bg-surface fixed inset-x-0 bottom-0 z-40 flex justify-around border-t p-1 pb-[calc(0.25rem+env(safe-area-inset-bottom))] md:hidden"
    >
      {visible.map((item) => (
        <Link
          key={item.id}
          to={item.path}
          activeOptions={{ exact: item.path === '/' }}
          className={linkClass}
          activeProps={{ className: 'active', 'aria-current': 'page' }}
        >
          <item.icon className="h-5 w-5 [.active_&]:fill-current" aria-hidden="true" />
          {item.label}
        </Link>
      ))}
      {overflow.length > 0 && <MoreSheet items={overflow} />}
    </nav>
  );
}

function MoreSheet({ items }: { items: NavItem[] }): ReactElement {
  const [open, setOpen] = useState(false);
  const titleId = useId();

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button type="button" className={linkClass}>
          <Ellipsis className="h-5 w-5" aria-hidden="true" />
          More
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content
          aria-labelledby={titleId}
          className="border-border bg-surface shadow-overlay fixed inset-x-0 bottom-0 rounded-t-lg border p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]"
        >
          <div className="mb-2 flex items-center justify-between">
            <Dialog.Title id={titleId} className="text-text text-sm font-medium">
              More
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Close"
                className="text-text-muted focus-visible:outline-accent flex h-11 w-11 items-center justify-center rounded-md focus-visible:outline focus-visible:outline-2"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </Dialog.Close>
          </div>
          <ul className="flex flex-col gap-1">
            {items.map((item) => (
              <li key={item.id}>
                <Link
                  to={item.path}
                  onClick={() => setOpen(false)}
                  className="text-text flex items-center gap-3 rounded-md px-3 py-2 text-sm"
                >
                  <item.icon className="h-5 w-5" aria-hidden="true" />
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
