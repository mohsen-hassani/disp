import { defineConfig } from '@hey-api/openapi-ts';

// WEB-SPEC §6.1. `input` is the backend's `./dev openapi` output (repo root,
// two levels up from clients/web/). Output is committed — a clean checkout
// must build with no backend running (§25 criterion 1).
//
// Deviates from the spec's literal snippet in one way: `output.lint` is
// dropped (and its `format` replacement moved to `postProcess`, per the
// deprecation notice `@hey-api/openapi-ts` prints for both keys). Running
// ESLint as a post-processor over src/api/generated directly contradicts
// §6.2's own requirement that "ESLint MUST ignore that directory" — with
// that ignore in place (eslint.config.js), invoking `eslint <that path>`
// during codegen fails outright ("all matching files are ignored" is a hard
// error as of ESLint 9+, not the silent no-op it used to be). Prettier-only
// post-processing satisfies §6.2's real intent (generated code doesn't need
// linting as part of normal `eslint .` runs) without the contradiction.
export default defineConfig({
  input: '../../openapi.json',
  output: { path: 'src/api/generated', postProcess: ['prettier'] },
  plugins: [
    '@hey-api/client-fetch',
    '@hey-api/typescript',
    '@hey-api/sdk',
    '@tanstack/react-query',
  ],
});
