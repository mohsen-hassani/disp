import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { tanstackRouter } from '@tanstack/router-plugin/vite';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// WEB-SPEC §24.1: the only build-time value besides Vite's own import.meta.env
// is __APP_VERSION__, sourced from package.json. There is no other runtime
// configuration (no VITE_API_URL, no config.json fetch) — §2.1 requires the
// client and API to be same-origin with relative /api/... URLs always.
const pkg = JSON.parse(
  readFileSync(fileURLToPath(new URL('./package.json', import.meta.url)), 'utf-8'),
) as { version: string };

export default defineConfig({
  plugins: [
    // Must run before @vitejs/plugin-react: it generates src/routeTree.gen.ts
    // from src/routes/* and (via autoCodeSplitting) rewrites each route's
    // heavy exports into their own chunk — WEB-SPEC §9's "every route is a
    // lazy chunk" requirement, without hand-written React.lazy() per route.
    tanstackRouter({ target: 'react', autoCodeSplitting: true }),
    react(),
    tailwindcss(),
  ],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
});
