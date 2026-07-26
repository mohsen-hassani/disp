import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';

import { ShortcutsDialog } from '../../../src/components/shortcuts/ShortcutsDialog';

it('lists the §16.5 shortcuts when open', () => {
  render(<ShortcutsDialog open onOpenChange={() => {}} />);

  expect(screen.getByText('Go to dashboard')).toBeInTheDocument();
  expect(screen.getByText('Go to notes')).toBeInTheDocument();
  expect(screen.getByText('New note dialog')).toBeInTheDocument();
});

it('renders nothing visible when closed', () => {
  render(<ShortcutsDialog open={false} onOpenChange={() => {}} />);

  expect(screen.queryByText('Go to dashboard')).not.toBeInTheDocument();
});
