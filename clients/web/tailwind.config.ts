import type { Config } from 'tailwindcss';

// Design tokens (WEB-SPEC Appendix C) live in src/styles/index.css via the
// Tailwind v4 `@theme` directive, and content detection is automatic under
// the `@tailwindcss/vite` plugin (vite.config.ts). This file exists mainly so
// editor tooling (e.g. the Tailwind CSS IntelliSense extension) can find the
// project root; there is deliberately nothing else to configure here.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
} satisfies Config;
