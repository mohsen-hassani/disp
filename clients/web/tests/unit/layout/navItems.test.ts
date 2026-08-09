import { expect, it } from 'vitest';

import type { ModuleManifestOut } from '../../../src/api/generated';
import { computeNavSections, flattenNavSections } from '../../../src/components/layout/navItems';
import { FALLBACK_ICON } from '../../../src/lib/icons';

function makeModule(
  domain: string,
  clientNav?: ModuleManifestOut['client_nav'],
): ModuleManifestOut {
  return {
    domain,
    name: domain,
    version: '1.0.0',
    description: null,
    tiles: [],
    settings_panels: [],
    notification_types: [],
    client_nav: clientNav ?? null,
  };
}

const ids = (sections: ReturnType<typeof computeNavSections>): string[] =>
  flattenNavSections(sections).map((item) => item.id);

it('always includes Dashboard and Settings, in order', () => {
  const sections = computeNavSections({ modules: [], isAdmin: false });
  expect(ids(sections)).toEqual(['dashboard', 'settings']);
});

it('omits the Modules section entirely when no module has screens', () => {
  const sections = computeNavSections({ modules: [], isAdmin: false });
  expect(sections.map((section) => section.id)).toEqual(['primary', 'system']);
  expect(sections.some((section) => section.label === 'Modules')).toBe(false);
});

it('groups modules with screens under a labelled Modules section', () => {
  const sections = computeNavSections({
    modules: [makeModule('notes', { label: 'Notes', icon: 'sticky-note', order: 10 })],
    isAdmin: false,
  });

  expect(sections.map((section) => section.id)).toEqual(['primary', 'modules', 'system']);
  const modules = sections.find((section) => section.id === 'modules');
  expect(modules?.label).toBe('Modules');
  expect(modules?.items).toHaveLength(1);
  expect(modules?.items[0]).toMatchObject({ id: 'notes', path: '/notes', label: 'Notes' });
});

it('takes the label from the manifest, not from the client', () => {
  const sections = computeNavSections({
    modules: [makeModule('notes', { label: 'My Notebook', icon: 'sticky-note' })],
    isAdmin: false,
  });

  const item = flattenNavSections(sections).find((entry) => entry.id === 'notes');
  expect(item?.label).toBe('My Notebook');
});

it('hides a module that declares client_nav but has no screens in this client', () => {
  // The honesty half of §12.2: the server can declare a nav entry, but a
  // client without the screens must not pretend it has them. Nav is the
  // intersection of the manifest and MODULE_SCREENS, never just the manifest.
  const sections = computeNavSections({
    modules: [makeModule('futuremod', { label: 'Future', icon: 'box' })],
    isAdmin: false,
  });

  expect(ids(sections)).toEqual(['dashboard', 'settings']);
});

it('hides a module with screens that does not declare client_nav', () => {
  const sections = computeNavSections({ modules: [makeModule('notes')], isAdmin: false });
  expect(ids(sections)).toEqual(['dashboard', 'settings']);
});

it('orders module entries by the manifest-declared order, not manifest position', () => {
  const sections = computeNavSections({
    modules: [
      makeModule('zeta', { label: 'Zeta', icon: 'box', order: 90 }),
      makeModule('alpha', { label: 'Alpha', icon: 'box', order: 10 }),
    ],
    isAdmin: false,
    screens: new Set(['zeta', 'alpha']),
  });

  const modules = sections.find((section) => section.id === 'modules');
  expect(modules?.items.map((item) => item.id)).toEqual(['alpha', 'zeta']);
});

it('breaks an order tie by domain, so the nav never reshuffles between renders', () => {
  const sections = computeNavSections({
    modules: [
      makeModule('beta', { label: 'Beta', icon: 'box', order: 10 }),
      makeModule('alpha', { label: 'Alpha', icon: 'box', order: 10 }),
    ],
    isAdmin: false,
    screens: new Set(['beta', 'alpha']),
  });

  const modules = sections.find((section) => section.id === 'modules');
  expect(modules?.items.map((item) => item.id)).toEqual(['alpha', 'beta']);
});

it('falls back to a placeholder icon for a name this client does not carry', () => {
  // A module may name any lucide icon; this client only bundles an allow-list
  // of them. An unrecognised name must degrade, never break the nav.
  const sections = computeNavSections({
    modules: [makeModule('notes', { label: 'Notes', icon: 'not-a-real-icon' })],
    isAdmin: false,
  });

  const item = flattenNavSections(sections).find((entry) => entry.id === 'notes');
  expect(item?.icon).toBe(FALLBACK_ICON);
});

it('appends the admin-only Invitations item, marked desktopOnly, only when isAdmin', () => {
  const withoutAdmin = computeNavSections({ modules: [], isAdmin: false });
  expect(
    flattenNavSections(withoutAdmin).find((item) => item.id === 'admin-invites'),
  ).toBeUndefined();

  const withAdmin = computeNavSections({ modules: [], isAdmin: true });
  const invites = flattenNavSections(withAdmin).find((item) => item.id === 'admin-invites');
  expect(invites).toMatchObject({ path: '/admin/invites', desktopOnly: true });
});
