import { useQuery } from '@tanstack/react-query';
import { createFileRoute, Link } from '@tanstack/react-router';
import type { ReactElement } from 'react';

import { dashboardManifestQueryOptions } from '../api/queries';

export const Route = createFileRoute('/_app/settings/')({
  component: SettingsIndexPage,
  staticData: { title: 'Settings · DISP' },
});

const linkClass =
  'border-border bg-surface text-text focus-visible:outline-accent block rounded-md border p-3 text-sm font-medium hover:bg-surface-raised focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2';

// §14.1: every settings panel across all modules, grouped by module, plus
// the fixed Account and API tokens entries (M07 owns those two screens —
// this index only links to them).
function SettingsIndexPage(): ReactElement {
  const manifestQuery = useQuery(dashboardManifestQueryOptions());
  const modulesWithPanels = (manifestQuery.data?.modules ?? []).filter(
    (module) => module.settings_panels.length > 0,
  );

  return (
    <>
      <h1>Settings</h1>
      <nav aria-label="Settings sections" className="mt-4 flex flex-col gap-4">
        <ul className="flex flex-col gap-2">
          <li>
            <Link to="/settings/account" className={linkClass}>
              Account
            </Link>
          </li>
          <li>
            <Link to="/settings/tokens" className={linkClass}>
              API tokens
            </Link>
          </li>
        </ul>

        {modulesWithPanels.map((module) => (
          <div key={module.domain}>
            <p className="text-text-muted mb-2 text-xs tracking-wide uppercase">{module.name}</p>
            <ul className="flex flex-col gap-2">
              {module.settings_panels.map((panel) => (
                <li key={panel.key}>
                  <Link
                    to="/settings/$domain"
                    params={{ domain: module.domain }}
                    className={linkClass}
                  >
                    {panel.title}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
    </>
  );
}
