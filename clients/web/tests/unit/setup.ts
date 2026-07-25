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

// jsdom doesn't implement ResizeObserver at all — Radix's Switch (and other
// primitives using `@radix-ui/react-use-size`) call it unconditionally on
// mount, so any test rendering one throws `ResizeObserver is not defined`
// without this stub. No test asserts on resize behavior, so a no-op is enough.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver ??= ResizeObserverStub;
