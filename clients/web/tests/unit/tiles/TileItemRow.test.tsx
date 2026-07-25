import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { TileItemRow } from '../../../src/components/tiles/TileItemRow';
import { makeTileItem } from './fixtures';
import { renderTile } from './testUtils';

// Test 26.
describe('TileItemRow href translation', () => {
  it('renders a mapped href as a router link', async () => {
    await renderTile(
      <ul>
        <TileItemRow item={makeTileItem({ href: '/api/notes/abc' })} />
      </ul>,
    );
    expect(screen.getByRole('link', { name: /item one/i })).toHaveAttribute('href', '/notes/abc');
  });

  it('renders an unmapped href as plain text, not a link', async () => {
    await renderTile(
      <ul>
        <TileItemRow item={makeTileItem({ href: '/api/unregistered-module/abc' })} />
      </ul>,
    );
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByText('Item one')).toBeInTheDocument();
  });
});

// Test 25.
describe('TileItemRow done rendering', () => {
  it('renders a disabled, read-only checkbox that cannot be toggled', async () => {
    await renderTile(
      <ul>
        <TileItemRow item={makeTileItem({ done: false })} />
      </ul>,
    );
    const checkbox = screen.getByRole('checkbox', { name: /read-only in this version/i });
    expect(checkbox).toBeDisabled();
    expect(checkbox).not.toBeChecked();
    expect(checkbox).toHaveAttribute('aria-readonly', 'true');
    // A disabled control can't receive a real click event from the browser
    // at all — there's nothing further to fire; this asserts the state
    // that guarantees it stays inert.
  });

  it('omits the checkbox entirely when done is absent', async () => {
    await renderTile(
      <ul>
        <TileItemRow item={makeTileItem()} />
      </ul>,
    );
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });
});
