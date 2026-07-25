import type { TileSpec } from '../../api/generated';
import { MODULE_ROUTES } from '../layout/navItems';

const API_PREFIX = '/api';

/** §13.2: a stable, server-controlled sort — `order` ascending, then `key` ascending. */
export function sortTileSpecs<T extends Pick<TileSpec, 'order' | 'key'>>(specs: T[]): T[] {
  return [...specs].sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || a.key.localeCompare(b.key));
}

/**
 * §13.7: strip the `/api` prefix and check the result against M04's
 * `MODULE_ROUTES` map — the one generic rule, with no per-module case.
 * Returns `null` for anything that isn't `/api/...` or whose module has no
 * registered screen, in which case the caller renders plain text instead
 * of a broken link.
 */
export function translateTileHref(href: string): string | null {
  if (!href.startsWith(`${API_PREFIX}/`)) {
    return null;
  }
  const stripped = href.slice(API_PREFIX.length);
  const domain = stripped.split('/').filter(Boolean)[0];
  return domain && domain in MODULE_ROUTES ? stripped : null;
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
