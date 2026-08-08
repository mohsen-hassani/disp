#!/usr/bin/env node
// Enforces the §22 performance budget table against a real `pnpm build`
// output — CI fails, not just a printed warning, so these stay hard gates
// the same way the backend's coverage percentages are.
//
// Usage: node scripts/check-bundle-budget.mjs   (run after `vite build`)
//
// Reads dist/.vite/manifest.json (see vite.config.ts's `build.manifest`) to
// tell the true entry chunk's static-import closure (what a first page load
// actually downloads before paint) apart from route-level dynamic imports
// (what §22 calls the "largest route chunk" — loaded on navigation, not
// upfront). A plain `du -h dist/assets` can't make that distinction; the
// manifest can.
import { gzipSync } from 'node:zlib';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const DIST = join(import.meta.dirname, '..', 'dist');
const BUDGETS = {
  initialJsGzip: 200 * 1024,
  initialCssGzip: 30 * 1024,
  largestRouteChunkGzip: 80 * 1024,
};

const manifest = JSON.parse(readFileSync(join(DIST, '.vite', 'manifest.json'), 'utf-8'));

function gzipSize(distRelativeFile) {
  return gzipSync(readFileSync(join(DIST, distRelativeFile)), { level: 9 }).length;
}

const entryKey = Object.keys(manifest).find((key) => manifest[key].isEntry);
if (!entryKey) {
  console.error('check-bundle-budget: no entry chunk found in dist/.vite/manifest.json');
  process.exit(1);
}
const entry = manifest[entryKey];

// Static-import closure = everything downloaded before first paint.
const initialJsFiles = new Set([entry.file]);
const initialCssFiles = new Set(entry.css ?? []);
const seen = new Set([entryKey]);
const queue = [...(entry.imports ?? [])];
while (queue.length > 0) {
  const key = queue.shift();
  if (seen.has(key)) continue;
  seen.add(key);
  const chunk = manifest[key];
  if (!chunk) continue;
  initialJsFiles.add(chunk.file);
  for (const css of chunk.css ?? []) initialCssFiles.add(css);
  for (const dep of chunk.imports ?? []) queue.push(dep);
}

const initialJsGzip = [...initialJsFiles].reduce((sum, f) => sum + gzipSize(f), 0);
const initialCssGzip = [...initialCssFiles].reduce((sum, f) => sum + gzipSize(f), 0);

// Route chunks = the entry's direct dynamic imports that are route files
// (tanstack-router's ?tsr-split=component/notFoundComponent convention) —
// excludes non-route dynamic imports (e.g. workbox-window) and excludes
// chunks lazy-loaded *within* a route (like TileActionDialog), which aren't
// "route chunks" in §22's sense.
//
// Each route's own generated wrapper chunk is thin glue that *statically*
// imports the real page implementation one level deeper (e.g. the notes
// detail route pulls in NoteEditor this way) — measuring only the wrapper
// itself would badly undercount what navigating to that route actually
// costs. Walk each route's own static-import closure instead, the same way
// the "initial" closure above is walked, but only counting weight *not*
// already paid for by the initial load (shared chunks already downloaded
// don't cost anything extra when a route is entered).
const routeChunkKeys = (entry.dynamicImports ?? []).filter((key) => key.includes('?tsr-split='));
let largestRouteChunkGzip = 0;
let largestRouteChunkName = null;
for (const rootKey of routeChunkKeys) {
  const rootChunk = manifest[rootKey];
  if (!rootChunk) continue;
  const routeFiles = new Set();
  const routeSeen = new Set();
  const routeQueue = [rootKey];
  while (routeQueue.length > 0) {
    const key = routeQueue.shift();
    if (routeSeen.has(key)) continue;
    routeSeen.add(key);
    const chunk = manifest[key];
    if (!chunk) continue;
    if (!initialJsFiles.has(chunk.file)) routeFiles.add(chunk.file);
    for (const dep of chunk.imports ?? []) routeQueue.push(dep);
  }
  const size = [...routeFiles].reduce((sum, f) => sum + gzipSize(f), 0);
  if (size > largestRouteChunkGzip) {
    largestRouteChunkGzip = size;
    largestRouteChunkName = rootChunk.file;
  }
}

const results = [
  ['Initial JS', initialJsGzip, BUDGETS.initialJsGzip],
  ['Initial CSS', initialCssGzip, BUDGETS.initialCssGzip],
  [
    `Largest route chunk (${largestRouteChunkName ?? 'none'})`,
    largestRouteChunkGzip,
    BUDGETS.largestRouteChunkGzip,
  ],
];

let failed = false;
for (const [label, actual, budget] of results) {
  const ok = actual <= budget;
  if (!ok) failed = true;
  console.log(
    `${ok ? 'PASS' : 'FAIL'}  ${label}: ${(actual / 1024).toFixed(1)}KB (budget ${(budget / 1024).toFixed(0)}KB)`,
  );
}

if (failed) {
  console.error(
    '\nBundle budget exceeded — see §22 of milestones/client/M12-pwa-deploy-acceptance.md.',
  );
  process.exit(1);
}
