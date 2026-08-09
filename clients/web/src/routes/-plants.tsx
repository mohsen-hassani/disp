import type { ReactElement } from 'react';

import { PlantList } from '../components/plants/PlantList';

interface PlantsListPageProps {
  q: string | undefined;
  onQChange: (q: string | undefined) => void;
}

// Router-ignored (leading `-`) — see `-login.tsx`'s doc for why. `q` and its
// setter come in as plain props (mirrors `-notes.tsx`) rather than this
// file reading `useSearch`/`useNavigate` itself, so it stays testable with
// plain props and no router search machinery.
export function PlantsListPage({ q, onQChange }: PlantsListPageProps): ReactElement {
  return (
    <>
      <h1>Plants</h1>
      <PlantList q={q} onQChange={onQChange} />
    </>
  );
}
