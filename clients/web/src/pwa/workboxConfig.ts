import type { VitePWAOptions } from 'vite-plugin-pwa';

// Reached via `vite-plugin-pwa`'s own public type surface (a direct
// dependency) rather than importing `workbox-build` directly (a nested
// dependency pnpm's strict layout won't resolve from here).
type WorkboxOptions = NonNullable<VitePWAOptions['workbox']>;
type RuntimeCachingEntry = NonNullable<WorkboxOptions['runtimeCaching']>[number];

/**
 * §18.2's caching table, shared between `vite.config.ts` (which feeds this
 * to `VitePWA({ workbox: ... })`) and `tests/unit/pwa/workboxConfig.test.ts`
 * (which asserts against it directly) — a build-only test would mean this
 * table's shape is only ever checked by eyeballing a generated `sw.js`.
 */
export function buildRuntimeCaching(cacheVersion: string): RuntimeCachingEntry[] {
  return [
    // Never cached, ever — checked first so nothing below can shadow it.
    {
      urlPattern: /^\/api\/auth\//,
      method: 'GET',
      handler: 'NetworkOnly',
    },
    {
      urlPattern: ({ url }: { url: URL }) => url.pathname === '/api/dashboard/manifest',
      method: 'GET',
      handler: 'StaleWhileRevalidate',
      options: {
        cacheName: `dashboard-manifest-v${cacheVersion}`,
        expiration: { maxEntries: 1, maxAgeSeconds: 24 * 60 * 60 },
        cacheableResponse: { statuses: [200] },
      },
    },
    {
      urlPattern: /^\/api\/dashboard\/tiles/,
      method: 'GET',
      handler: 'NetworkFirst',
      options: {
        cacheName: `dashboard-tiles-v${cacheVersion}`,
        networkTimeoutSeconds: 3,
        expiration: { maxEntries: 20, maxAgeSeconds: 60 * 60 },
        cacheableResponse: { statuses: [200] },
      },
    },
    {
      urlPattern: ({ url }: { url: URL }) => url.pathname === '/api/notes',
      method: 'GET',
      handler: 'NetworkFirst',
      options: {
        cacheName: `notes-list-v${cacheVersion}`,
        networkTimeoutSeconds: 3,
        expiration: { maxEntries: 30, maxAgeSeconds: 24 * 60 * 60 },
        cacheableResponse: { statuses: [200] },
      },
    },
    {
      urlPattern: /^\/api\/notes\//,
      method: 'GET',
      handler: 'NetworkFirst',
      options: {
        cacheName: `notes-detail-v${cacheVersion}`,
        networkTimeoutSeconds: 3,
        expiration: { maxEntries: 50, maxAgeSeconds: 24 * 60 * 60 },
        cacheableResponse: { statuses: [200] },
      },
    },
    {
      urlPattern: /^\/api\/settings\//,
      method: 'GET',
      handler: 'NetworkFirst',
      options: {
        cacheName: `settings-v${cacheVersion}`,
        networkTimeoutSeconds: 3,
        expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 },
        cacheableResponse: { statuses: [200] },
      },
    },
    // Any non-GET /api/** — never cached, registered once per method since
    // workbox routes are method-specific.
    ...(['POST', 'PUT', 'PATCH', 'DELETE'] as const).map((method) => ({
      urlPattern: /^\/api\//,
      method,
      handler: 'NetworkOnly' as const,
    })),
  ];
}

export const PWA_MANIFEST = {
  // §17's "DISP naming applied here": renamed from the spec's literal "MyStuff".
  name: 'DISP',
  short_name: 'DISP',
  description: 'Your personal control centre',
  start_url: '/',
  scope: '/',
  display: 'standalone' as const,
  orientation: 'any' as const,
  background_color: '#ffffff',
  // §17.1: matches the light-theme surface — src/lib/theme.ts owns keeping
  // the *runtime* <meta name="theme-color"> in sync with the resolved theme
  // after this initial value.
  theme_color: '#ffffff',
  icons: [
    { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
    { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
    {
      src: '/icons/icon-maskable-192.png',
      sizes: '192x192',
      type: 'image/png',
      purpose: 'maskable',
    },
    {
      src: '/icons/icon-maskable-512.png',
      sizes: '512x512',
      type: 'image/png',
      purpose: 'maskable',
    },
  ],
  shortcuts: [
    {
      name: 'New note',
      url: '/notes?new=1',
      icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }],
    },
  ],
};
