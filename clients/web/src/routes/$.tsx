import { createFileRoute } from '@tanstack/react-router';

import { NotFoundPage } from './-not-found';

// WEB-SPEC §9 lists this file as `$404.tsx`, but that's not actually
// TanStack Router's catch-all convention — a leading `$` followed by more
// characters (`$404`) is a *named* dynamic param ("404", not even a valid
// JS identifier — the generator warns) matching exactly one path segment,
// not a catch-all. The real splat file name is a bare `$` (confirmed
// against @tanstack/router-generator: only a literal `$` segment produces
// the internal `_splat` param the router treats as "match anything").
export const Route = createFileRoute('/$')({
  component: NotFoundPage,
  staticData: { title: 'Not found · DISP' },
});
