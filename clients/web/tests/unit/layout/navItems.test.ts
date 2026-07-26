import { expect, it } from 'vitest';

import { computeNavItems } from '../../../src/components/layout/navItems';

it('always includes Dashboard and Settings, in order', () => {
  const items = computeNavItems({ manifestDomains: [], isAdmin: false });
  expect(items.map((item) => item.id)).toEqual(['dashboard', 'settings']);
});

it('inserts a module screen for a domain with a registered route, ignoring unknown domains', () => {
  const items = computeNavItems({ manifestDomains: ['notes', 'unknown-module'], isAdmin: false });
  expect(items.map((item) => item.id)).toEqual(['dashboard', 'notes', 'settings']);
  expect(items.find((item) => item.id === 'notes')).toMatchObject({
    path: '/notes',
    label: 'Notes',
    desktopOnly: false,
  });
});

it('appends the admin-only Invitations item, marked desktopOnly, only when isAdmin', () => {
  const withoutAdmin = computeNavItems({ manifestDomains: [], isAdmin: false });
  expect(withoutAdmin.find((item) => item.id === 'admin-invites')).toBeUndefined();

  const withAdmin = computeNavItems({ manifestDomains: [], isAdmin: true });
  const invites = withAdmin.find((item) => item.id === 'admin-invites');
  expect(invites).toMatchObject({ path: '/admin/invites', desktopOnly: true });
});
