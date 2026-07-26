import { expect, it } from 'vitest';

import { buildRuntimeCaching, PWA_MANIFEST } from '../../../src/pwa/workboxConfig';

// Case 45 (config half — the build-output half is verified by actually
// running `pnpm build` and inspecting dist/sw.js, per the milestone's own
// verification section; this asserts the *source* the service worker is
// generated from).
it('never caches any /api/auth/* request (case 45)', () => {
  const entries = buildRuntimeCaching('1.0.0');
  const authEntry = entries.find(
    (entry) => entry.urlPattern instanceof RegExp && entry.urlPattern.test('/api/auth/me'),
  );

  expect(authEntry).toBeDefined();
  expect(authEntry?.handler).toBe('NetworkOnly');
});

it('never caches a non-GET /api/** request, for every mutating method', () => {
  const entries = buildRuntimeCaching('1.0.0');
  for (const method of ['POST', 'PUT', 'PATCH', 'DELETE'] as const) {
    const entry = entries.find(
      (candidate) =>
        candidate.method === method &&
        candidate.urlPattern instanceof RegExp &&
        candidate.urlPattern.test('/api/notes'),
    );
    expect(entry?.handler).toBe('NetworkOnly');
  }
});

it('caches GET /api/notes and /api/notes/:id with NetworkFirst, only 200s, and the app version in the cache name', () => {
  const entries = buildRuntimeCaching('1.2.3');

  const notesList = entries.find(
    (entry) =>
      entry.method === 'GET' &&
      typeof entry.urlPattern === 'function' &&
      entry.urlPattern({ url: new URL('http://localhost/api/notes') } as never),
  );
  expect(notesList?.handler).toBe('NetworkFirst');
  expect(notesList?.options?.cacheName).toBe('notes-list-v1.2.3');
  expect(notesList?.options?.cacheableResponse).toEqual({ statuses: [200] });

  const notesDetail = entries.find(
    (entry) =>
      entry.method === 'GET' &&
      entry.urlPattern instanceof RegExp &&
      entry.urlPattern.test('/api/notes/abc-123'),
  );
  expect(notesDetail?.handler).toBe('NetworkFirst');
  expect(notesDetail?.options?.cacheName).toBe('notes-detail-v1.2.3');
});

it('caches the dashboard manifest with StaleWhileRevalidate and a single-entry expiration', () => {
  const entries = buildRuntimeCaching('1.0.0');
  const manifestEntry = entries.find(
    (entry) =>
      typeof entry.urlPattern === 'function' &&
      entry.urlPattern({ url: new URL('http://localhost/api/dashboard/manifest') } as never),
  );

  expect(manifestEntry?.handler).toBe('StaleWhileRevalidate');
  expect(manifestEntry?.options?.expiration).toEqual({ maxEntries: 1, maxAgeSeconds: 86_400 });
});

it('renders the DISP-branded manifest, not the spec draft\'s "MyStuff"', () => {
  expect(PWA_MANIFEST.name).toBe('DISP');
  expect(PWA_MANIFEST.short_name).toBe('DISP');
  expect(PWA_MANIFEST.shortcuts).toEqual([
    {
      name: 'New note',
      url: '/notes?new=1',
      icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }],
    },
  ]);
});
