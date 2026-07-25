import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import './styles/index.css';

// Trivial bootstrap so `pnpm build` produces a working dist/ from M01 onward
// (WEB-SPEC's own bar for this milestone). Providers, the router, and
// AuthProvider are wired in by M02-M04.
const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element #root not found');
}

createRoot(rootElement).render(
  <StrictMode>
    <div />
  </StrictMode>,
);
