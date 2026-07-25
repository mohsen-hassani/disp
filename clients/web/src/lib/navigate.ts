// No router exists yet — M04 builds TanStack Router. Auth code (M03) still
// needs to redirect (login → next, guards → /login?next=, logout → /login),
// so this is a minimal, swappable navigation primitive rather than a
// special-cased "no router" branch scattered through auth/.
//
// M04 should call setNavigate(router.navigate) once the real router exists,
// replacing the full-page-reload fallback below with client-side
// navigation. The fallback is not broken in the meantime: a full reload
// still lands on a working page, since AuthProvider re-bootstraps from the
// HttpOnly refresh cookie on every mount exactly as the first page load
// would (§8.3) — just one avoidable network round-trip until M04 lands.
let navigateImpl: (path: string) => void = (path) => {
  window.location.assign(path);
};

export function navigate(path: string): void {
  navigateImpl(path);
}

export function setNavigate(fn: (path: string) => void): void {
  navigateImpl = fn;
}
