import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PlantThumbnail } from '../../../src/components/plants/PlantThumbnail';

describe('PlantThumbnail', () => {
  it('renders a placeholder when has_image is false', () => {
    render(<PlantThumbnail imageUrl={null} hasImage={false} name="Monstera" />);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('renders the image when has_image is true and the url is set', () => {
    render(<PlantThumbnail imageUrl="/api/plants/plant-1/image" hasImage name="Monstera" />);
    expect(screen.getByRole('img', { name: 'Monstera' })).toBeInTheDocument();
  });

  // Case 4 (M14 §7): `has_image: true` with a 404 image (e.g. a
  // database-only restore where the file on the media volume is gone, per
  // `CLAUDE.md`'s plants gotchas) must render a placeholder, never a broken
  // `<img>`.
  it('falls back to a placeholder if the image fails to load', () => {
    render(<PlantThumbnail imageUrl="/api/plants/plant-1/image" hasImage name="Monstera" />);
    const img = screen.getByRole('img', { name: 'Monstera' });

    fireEvent.error(img);

    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });
});
