import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Vitest, unlike Jest, doesn't auto-register RTL's cleanup between tests —
// without this, successive `render()` calls across tests (or even within
// one file) leave every previous render's DOM mounted, breaking any query
// that expects a single match.
afterEach(() => {
  cleanup();
});
