/**
 * The domains this client ships bespoke screens for.
 *
 * WEB-SPEC §12.2: a module's nav entry, route namespace and tile nav button
 * are declared server-side in its manifest (`client_nav`), but the server
 * can't ship React. So navigation is the *intersection* of two facts:
 *
 *   server (manifest.client_nav) — this module wants to be reachable, here's
 *                                  its label, icon and order
 *   client (this set)           — the screens actually exist
 *
 * A module declaring `client_nav` that this client has no screens for renders
 * on the dashboard only, exactly as if it had declared nothing. That keeps
 * §12.2's original rule intact — the client never links to a screen it
 * doesn't have — while moving every piece of *presentation* to the server.
 *
 * Adding a module's screens is one line here plus the route files. Nothing
 * else in the shell changes: no label, no icon, no path, no ordering.
 */
export const MODULE_SCREENS: ReadonlySet<string> = new Set(['notes', 'plants']);

/** Routes live at /<domain>/… — derived from the domain, never declared. */
export function moduleBasePath(domain: string): string {
  return `/${domain}`;
}

/**
 * The domains that may be linked to: declared by the server *and* implemented
 * here. Shared by the nav (which entries to render) and tile href translation
 * (which deep links become real links), so the two can never disagree about
 * what is reachable.
 */
export function navigableDomains(
  modules: readonly { domain: string; client_nav?: unknown }[] | undefined,
): ReadonlySet<string> {
  return new Set(
    (modules ?? [])
      .filter((module) => module.client_nav != null && MODULE_SCREENS.has(module.domain))
      .map((module) => module.domain),
  );
}
