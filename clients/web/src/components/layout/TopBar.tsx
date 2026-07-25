import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Link } from '@tanstack/react-router';
import { Check, ChevronDown, LogOut, Monitor, Moon, Sun } from 'lucide-react';
import type { ReactElement } from 'react';

import { useAuth } from '../../auth/useAuth';
import { usePageTitle } from '../../hooks/usePageTitle';
import { cn } from '../../lib/cn';
import { type ThemePreference, useTheme } from '../../lib/theme';

const THEME_OPTIONS: Array<{ value: ThemePreference; label: string; Icon: typeof Sun }> = [
  { value: 'light', label: 'Light', Icon: Sun },
  { value: 'dark', label: 'Dark', Icon: Moon },
  { value: 'system', label: 'System', Icon: Monitor },
];

const itemClass =
  'flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-text outline-none data-highlighted:bg-surface-sunken';

export function TopBar(): ReactElement {
  const title = usePageTitle();
  const { state, logout } = useAuth();
  const { preference, setPreference } = useTheme();

  return (
    <header className="border-border bg-surface flex h-14 items-center justify-between border-b px-4 pt-[env(safe-area-inset-top)]">
      <div className="flex min-w-0 items-center gap-4">
        <Link
          to="/"
          className="text-accent focus-visible:outline-accent shrink-0 text-lg font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          DISP
        </Link>
        <h1 className="text-text truncate text-base font-medium">{title}</h1>
      </div>

      {state.status === 'authenticated' && (
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              type="button"
              className="text-text focus-visible:outline-accent flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              <span className="max-w-[10rem] truncate">{state.user.display_name}</span>
              <ChevronDown className="h-4 w-4 shrink-0" aria-hidden="true" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={8}
              className="border-border bg-surface-raised shadow-overlay w-64 rounded-md border p-1"
            >
              <div className="px-2 py-1.5">
                <p className="text-text truncate text-sm font-medium">{state.user.display_name}</p>
                <p className="text-text-muted truncate text-xs">{state.user.email}</p>
              </div>
              <DropdownMenu.Separator className="bg-border my-1 h-px" />

              <DropdownMenu.Item asChild className={itemClass}>
                <Link to="/settings/account">Account</Link>
              </DropdownMenu.Item>
              <DropdownMenu.Item asChild className={itemClass}>
                <Link to="/settings/tokens">API tokens</Link>
              </DropdownMenu.Item>

              <DropdownMenu.Sub>
                <DropdownMenu.SubTrigger className={cn(itemClass, 'justify-between')}>
                  Theme
                  <span className="text-text-muted text-xs capitalize">{preference}</span>
                </DropdownMenu.SubTrigger>
                <DropdownMenu.Portal>
                  <DropdownMenu.SubContent
                    sideOffset={4}
                    className="border-border bg-surface-raised shadow-overlay w-40 rounded-md border p-1"
                  >
                    {THEME_OPTIONS.map(({ value, label, Icon }) => (
                      <DropdownMenu.Item
                        key={value}
                        className={itemClass}
                        onSelect={() => setPreference(value)}
                      >
                        <Icon className="h-4 w-4" aria-hidden="true" />
                        <span className="flex-1">{label}</span>
                        {preference === value && <Check className="h-4 w-4" aria-hidden="true" />}
                      </DropdownMenu.Item>
                    ))}
                  </DropdownMenu.SubContent>
                </DropdownMenu.Portal>
              </DropdownMenu.Sub>

              <DropdownMenu.Separator className="bg-border my-1 h-px" />
              <DropdownMenu.Item className={itemClass} onSelect={() => void logout()}>
                <LogOut className="h-4 w-4" aria-hidden="true" />
                Sign out
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      )}
    </header>
  );
}
