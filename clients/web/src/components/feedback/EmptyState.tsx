import type { LucideIcon } from 'lucide-react';
import type { ReactElement, ReactNode } from 'react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  action?: ReactNode;
}

// WEB-SPEC §18.2: an icon, a one-line explanation, and — where an action
// makes sense — a primary button. Never an unstyled "No data". Formally
// M10's file (`components/feedback/`); pulled forward here because §13.9's
// empty dashboard needs it and M10 hasn't started — same call as M04 made
// for M06's SchemaForm.
export function EmptyState({ icon: Icon, title, action }: EmptyStateProps): ReactElement {
  return (
    <div className="border-border flex flex-col items-center gap-3 rounded-md border border-dashed p-8 text-center">
      <Icon className="text-text-muted h-8 w-8" aria-hidden="true" />
      <p className="text-text-muted text-sm">{title}</p>
      {action}
    </div>
  );
}
