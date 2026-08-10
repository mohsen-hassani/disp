import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { PlantThumbnail } from '../../../src/components/plants/PlantThumbnail';

// A minimal wrapper — PlantThumbnail only needs a QueryClient (for
// useQueryClient()/invalidateAffected), not the full router+manifest stack
// renderPlants sets up for router-aware components. Keeping our own
// QueryClient here also lets `rerender` swap `imageUrl` while preserving
// the same client, which the retry-reset behaviour under test depends on.
function renderThumbnail(element: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const utils = render(<QueryClientProvider client={queryClient}>{element}</QueryClientProvider>);
  return {
    ...utils,
    queryClient,
    rerenderWith: (next: ReactElement) =>
      utils.rerender(<QueryClientProvider client={queryClient}>{next}</QueryClientProvider>),
  };
}

describe('PlantThumbnail', () => {
  it('renders a placeholder when has_image is false', () => {
    renderThumbnail(
      <PlantThumbnail plantId="plant-1" imageUrl={null} hasImage={false} name="Monstera" />,
    );
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('renders the image when has_image is true and the url is set', () => {
    renderThumbnail(
      <PlantThumbnail
        plantId="plant-1"
        imageUrl="/api/files/asset-1?exp=1&sig=x"
        hasImage
        name="Monstera"
      />,
    );
    expect(screen.getByRole('img', { name: 'Monstera' })).toBeInTheDocument();
  });

  // M18-files.md §13: `image_url` is now a bucketed-expiry signed URL — the
  // first `onError` invalidates the owning queries (which re-mints the URL
  // on refetch) and retries, rather than falling straight back to the
  // placeholder. An `<img>` load never exposes an HTTP status, so an actual
  // 404 and a merely-expired signature look identical here; both get one
  // retry before giving up.
  it('invalidates the plants queries and keeps the image on the first failure', () => {
    const { queryClient } = renderThumbnail(
      <PlantThumbnail
        plantId="plant-1"
        imageUrl="/api/files/asset-1?exp=1&sig=x"
        hasImage
        name="Monstera"
      />,
    );
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    const img = screen.getByRole('img', { name: 'Monstera' });

    fireEvent.error(img);

    expect(invalidateSpy).toHaveBeenCalled();
    // Still showing the (not-yet-refetched) image, not the placeholder —
    // the fallback only happens after a *second* failure.
    expect(screen.getByRole('img', { name: 'Monstera' })).toBeInTheDocument();
  });

  it('falls back to the placeholder on a second failure of the same URL, without invalidating again', () => {
    const { queryClient } = renderThumbnail(
      <PlantThumbnail
        plantId="plant-1"
        imageUrl="/api/files/asset-1?exp=1&sig=x"
        hasImage
        name="Monstera"
      />,
    );
    const img = screen.getByRole('img', { name: 'Monstera' });

    fireEvent.error(img);
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    fireEvent.error(img);

    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    // The second failure (same URL, already retried) must not trigger
    // another invalidation — one retry per URL, not an invalidation loop.
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('gives a freshly re-minted URL its own retry after an earlier fallback', () => {
    const { queryClient, rerenderWith } = renderThumbnail(
      <PlantThumbnail
        plantId="plant-1"
        imageUrl="/api/files/asset-1?exp=1&sig=x"
        hasImage
        name="Monstera"
      />,
    );
    const firstImg = screen.getByRole('img', { name: 'Monstera' });
    fireEvent.error(firstImg);
    fireEvent.error(firstImg);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();

    // Simulate the invalidated query refetching with a re-minted signature.
    rerenderWith(
      <PlantThumbnail
        plantId="plant-1"
        imageUrl="/api/files/asset-1?exp=2&sig=y"
        hasImage
        name="Monstera"
      />,
    );
    expect(screen.getByRole('img', { name: 'Monstera' })).toBeInTheDocument();

    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    fireEvent.error(screen.getByRole('img', { name: 'Monstera' }));

    expect(invalidateSpy).toHaveBeenCalled();
    expect(screen.getByRole('img', { name: 'Monstera' })).toBeInTheDocument();
  });
});
