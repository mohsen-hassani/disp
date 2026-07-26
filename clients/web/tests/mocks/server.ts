import { setupServer } from 'msw/node';

import { handlers } from './handlers';

// §23.2: opt-in per test file (`server.listen()`/`resetHandlers()`/`close()`
// in that file's own lifecycle hooks) rather than started globally in
// `tests/unit/setup.ts` — every existing unit/component test already mocks
// `globalThis.fetch` directly per §8 (auth) and per-component test file, and
// running an MSW server unconditionally underneath all of them risks
// interfering with `vi.spyOn(globalThis, 'fetch')` in ways that would be
// hard to diagnose. A test file that wants MSW's typed multi-endpoint
// handlers instead of a hand-rolled fetch spy imports this directly.
export const server = setupServer(...handlers);
