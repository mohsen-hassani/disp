import { describe, expect, it } from 'vitest';

import { MODULE_SCREENS } from '../../../src/modules/registry';

// Test 27 / WEB-SPEC §13's own rule: "No component in
// `src/components/tiles/` may contain a conditional on a specific tile key
// or module domain." Written as this milestone's own test (not deferred to
// M11) so a regression is caught the moment someone reaches for
// `if (tile.key === '...')` under deadline pressure.
//
// `import.meta.glob` (Vite-native, works under Vitest without pulling in
// Node's `fs`/`path` types — this app's tsconfig deliberately doesn't
// include them, matching its browser-only `types` list) reads every tiles/
// source file as raw text at test time.
const tileFiles = import.meta.glob('../../../src/components/tiles/**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

describe('src/components/tiles has no module-domain string literals', () => {
  const domains = [...MODULE_SCREENS];
  const files = Object.entries(tileFiles);

  it('has at least one domain and one file to scan (a vacuous pass would hide a broken test)', () => {
    expect(domains.length).toBeGreaterThan(0);
    expect(files.length).toBeGreaterThan(0);
  });

  it.each(files)('%s contains no known module-domain literal', (_path, content) => {
    for (const domain of domains) {
      expect(content).not.toMatch(new RegExp(`\\b${domain}\\b`));
    }
  });
});
