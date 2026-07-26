import { render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';

import { OfflineBanner } from '../../../src/components/feedback/OfflineBanner';
import { setOnline } from './testUtils';

afterEach(() => {
  setOnline(true);
});

// Case 42 (banner half): appears whenever navigator.onLine is false.
it('renders nothing while online', () => {
  setOnline(true);
  render(<OfflineBanner />);

  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

it('appears when offline', () => {
  setOnline(false);
  render(<OfflineBanner />);

  expect(screen.getByRole('status')).toHaveTextContent("You're offline.");
});
