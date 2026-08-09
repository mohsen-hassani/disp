import type { TileSpec } from '../../api/generated';

const API_PREFIX = '/api';

/** §13.2: a stable, server-controlled sort — `order` ascending, then `key` ascending. */
export function sortTileSpecs<T extends Pick<TileSpec, 'order' | 'key'>>(specs: T[]): T[] {
  return [...specs].sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || a.key.localeCompare(b.key));
}

/**
 * §13.7: strip the `/api` prefix and check the domain against the set of
 * reachable ones — the one generic rule, with no per-module case. Returns
 * `null` for anything that isn't `/api/...` or whose module has no screens,
 * in which case the caller renders plain text instead of a broken link.
 *
 * `navigableDomains` is passed in rather than imported because it's now
 * derived from the manifest at runtime (see `modules/registry.ts`), not a
 * build-time constant. That's also why the transform stays a pure string
 * rewrite: a module's routes are always `/<domain>/…`, so the UI path is
 * exactly the API path minus `/api`.
 */
export function translateTileHref(
  href: string,
  navigableDomains: ReadonlySet<string>,
): string | null {
  if (!href.startsWith(`${API_PREFIX}/`)) {
    return null;
  }
  const stripped = href.slice(API_PREFIX.length);
  const domain = stripped.split('/').filter(Boolean)[0];
  return domain && navigableDomains.has(domain) ? stripped : null;
}

/** The `<domain>` half of a `<domain>.<name>` tile key. */
export function tileKeyDomain(key: string): string {
  return key.split('.')[0] ?? '';
}

/**
 * §13.6: a successful action invalidates the tile's own query key *and*
 * any query key whose first segment matches the action path's module
 * domain — derived generically from the path, not a per-module special
 * case. `/api/<domain>/...` → `[<domain>]`, matching every `qk.<domain>.*`
 * key as a TanStack Query prefix.
 */
export function actionDomainQueryKey(path: string): string[] {
  const withoutPrefix = path.startsWith(`${API_PREFIX}/`)
    ? path.slice(API_PREFIX.length + 1)
    : path;
  const domain = withoutPrefix.split('/').filter(Boolean)[0];
  return domain ? [domain] : [];
}
