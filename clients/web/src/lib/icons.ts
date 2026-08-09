import { Box, LayoutDashboard, Settings, Sprout, StickyNote, UserPlus } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

/**
 * Manifest-declared icons arrive as lucide's own kebab-case *names* — a
 * server can't send a React component. This allow-list is the name → component
 * mapping.
 *
 * Deliberately explicit rather than a dynamic `import('lucide-react')[name]`
 * lookup: lucide ships ~1500 icons and a dynamic key would defeat
 * tree-shaking, pulling all of them into the shell's chunk, which the nav
 * renders on every single page.
 *
 * A module can therefore name an icon this client doesn't carry. That's not
 * an error — it degrades to `Box` rather than breaking the nav, the same way
 * an unknown tile `size` falls back to `medium` (WEB-SPEC §13.2).
 */
const ICONS: Record<string, LucideIcon> = {
  box: Box,
  'layout-dashboard': LayoutDashboard,
  settings: Settings,
  sprout: Sprout,
  'sticky-note': StickyNote,
  'user-plus': UserPlus,
};

export const FALLBACK_ICON: LucideIcon = Box;

export function resolveIcon(name: string | undefined): LucideIcon {
  return (name && ICONS[name]) || FALLBACK_ICON;
}
