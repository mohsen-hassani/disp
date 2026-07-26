import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';

import { SavedDataLabel } from '../../../src/components/feedback/SavedDataLabel';

it('renders nothing when show is false', () => {
  render(<SavedDataLabel show={false} />);

  expect(screen.queryByText('Showing saved data.')).not.toBeInTheDocument();
});

it('renders the label when show is true', () => {
  render(<SavedDataLabel show />);

  expect(screen.getByText('Showing saved data.')).toBeInTheDocument();
});
