// M12 §22. Not yet wired into CI (see .github/workflows/web-ci.yml's header
// comment) — running `/` and `/notes` authenticated requires the e2e
// backend stack (docker-compose.e2e.yml) up first, which is a separable
// follow-up. Runnable locally today:
//
//   docker compose -f ../../docker-compose.yml -f ../../docker-compose.e2e.yml up -d
//   pnpm build && pnpm exec lhci autorun
//
// Default collection settings (unset throttlingMethod, mobile form-factor)
// already approximate §22's "simulated Fast 3G / 4x CPU" budget row — no
// manual throttling override needed.
//
// §22 lists Interaction to Next Paint as a Lighthouse CI metric, but a
// plain navigation-only collection (what `url` below produces) cannot
// actually measure INP — that needs a scripted user interaction mid-trace
// (Lighthouse's "user flow" API), which this config doesn't attempt. Total
// Blocking Time is used as the standard lab-metric proxy for responsiveness
// instead — a real substitution, documented here rather than silently
// treated as equivalent.
module.exports = {
  ci: {
    collect: {
      startServerCommand: 'pnpm preview --port 4173',
      startServerReadyPattern: 'Local:',
      url: ['http://localhost:4173/login', 'http://localhost:4173/', 'http://localhost:4173/notes'],
      puppeteerScript: './scripts/lighthouse-auth.cjs',
      numberOfRuns: 1,
    },
    assert: {
      assertions: {
        'categories:pwa': ['error', { minScore: 1 }],
        'largest-contentful-paint': ['error', { maxNumericValue: 2000 }],
        'cumulative-layout-shift': ['error', { maxNumericValue: 0.05 }],
        // TBT, not INP — see header comment.
        'total-blocking-time': ['warn', { maxNumericValue: 200 }],
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
  },
};
