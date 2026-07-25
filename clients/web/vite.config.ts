import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

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
  plugins: [react(), tailwindcss()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
});
