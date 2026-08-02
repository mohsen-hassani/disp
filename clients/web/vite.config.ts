import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { tanstackRouter } from '@tanstack/router-plugin/vite';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

import { buildRuntimeCaching, PWA_MANIFEST } from './src/pwa/workboxConfig';

// WEB-SPEC §24.1: the only build-time value besides Vite's own import.meta.env
// is __APP_VERSION__, sourced from package.json. There is no other runtime
// configuration (no VITE_API_URL, no config.json fetch) — §2.1 requires the
// client and API to be same-origin with relative /api/... URLs always.
const pkg = JSON.parse(
  readFileSync(fileURLToPath(new URL('./package.json', import.meta.url)), 'utf-8'),
) as { version: string };

// WEB-SPEC §18.3: "the cache name MUST include the app version so a deploy
// invalidates stale API caches automatically" — every cacheName below
// interpolates this, not just __APP_VERSION__ (the *runtime* define used
// everywhere else), because this file executes in Node at build time, one
// layer outside the bundle __APP_VERSION__ gets injected into.
const CACHE_VERSION = pkg.version;

export default defineConfig({
  plugins: [
    // Must run before @vitejs/plugin-react: it generates src/routeTree.gen.ts
    // from src/routes/* and (via autoCodeSplitting) rewrites each route's
    // heavy exports into their own chunk — WEB-SPEC §9's "every route is a
    // lazy chunk" requirement, without hand-written React.lazy() per route.
    tanstackRouter({ target: 'react', autoCodeSplitting: true }),
    react(),
    tailwindcss(),
    // WEB-SPEC §17/§18. `injectRegister: false` — src/pwa/registerSW.ts
    // registers the service worker itself via `virtual:pwa-register/react`'s
    // `useRegisterSW`, so the toast in UpdatePrompt.tsx has the `needRefresh`
    // state to react to; the plugin's own auto-injected script has no hook
    // into React state.
    VitePWA({
      registerType: 'prompt',
      injectRegister: false,
      includeAssets: [
        'favicon.svg',
        'icons/apple-touch-icon.png',
        'icons/icon-192.png',
        'icons/icon-512.png',
        'icons/icon-maskable-192.png',
        'icons/icon-maskable-512.png',
        'offline.html',
      ],
      manifest: PWA_MANIFEST,
      workbox: {
        cleanupOutdatedCaches: true,
        // App shell (JS/CSS/HTML/icons) precache, revisioned by build hash.
        globPatterns: ['**/*.{js,css,html,svg,png,ico}'],
        // §18.2: navigation requests fall back to the precached shell,
        // *excluding* any URL beginning with /api — an offline navigation to
        // an API URL must not silently return the app shell.
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: buildRuntimeCaching(CACHE_VERSION),
      },
    }),
  ],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  // WEB-SPEC §2.1/§23.4: e2e (Playwright, via `pnpm preview`) needs the same
  // same-origin shape production gets from Traefik's path-routing (§24.4) —
  // `/api`, `/health`, `/openapi.json` reaching the backend, everything else
  // served as the SPA. The real nginx/Traefik routing config is M12's job
  // (no `web` container image exists yet); this is a dev/preview-only
  // stand-in so pages calling the API reach it — `pnpm dev` and `pnpm
  // preview` share the same proxy shape (`server` and `preview` options
  // don't inherit from one another in Vite). Never used by `pnpm build`.
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/openapi.json': 'http://localhost:8000',
    },
  },
  preview: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/openapi.json': 'http://localhost:8000',
    },
  },
});
