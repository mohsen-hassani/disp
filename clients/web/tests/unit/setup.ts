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

// jsdom doesn't implement matchMedia at all — src/lib/theme.ts and
// src/hooks/useInstallPrompt.ts (system dark-mode / standalone-display-mode
// detection) call it unconditionally. A default-false stub is enough for
// tests that don't care about the result; tests that do (e.g.
// useInstallPrompt.test.ts) `vi.spyOn(window, 'matchMedia')` over this, which
// needs a real function already present to spy on in the first place.
window.matchMedia ??= (query: string): MediaQueryList =>
  ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }) as MediaQueryList;

// jsdom doesn't implement the Pointer Capture API — Radix's Toast (its
// swipe-to-dismiss gesture handling) calls `hasPointerCapture` on any
// pointer event targeting it, including a plain click on a `Toast.Action`
// button, which otherwise throws and fails the whole run via an unhandled
// exception rather than the specific test.
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.setPointerCapture ??= () => {};
Element.prototype.releasePointerCapture ??= () => {};
