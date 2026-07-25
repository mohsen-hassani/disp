import { defineConfig } from '@hey-api/openapi-ts';

// WEB-SPEC §6.1, verbatim. `input` is the backend's `./dev openapi` output
// (repo root, two levels up from clients/web/). Output is committed — a
// clean checkout must build with no backend running (§25 criterion 1).
export default defineConfig({
  input: '../../openapi.json',
  output: { path: 'src/api/generated', format: 'prettier', lint: 'eslint' },
  plugins: [
    '@hey-api/client-fetch',
    '@hey-api/typescript',
    '@hey-api/sdk',
    '@tanstack/react-query',
  ],
});
