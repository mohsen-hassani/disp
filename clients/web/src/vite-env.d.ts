/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

// Injected by vite.config.ts's `define` (WEB-SPEC §24.1) from package.json's
// version field — the only build-time value besides Vite's own import.meta.env.
declare const __APP_VERSION__: string;
