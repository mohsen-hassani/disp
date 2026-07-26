import { screen } from '@testing-library/react';
import { useEffect } from 'react';
import { expect, it } from 'vitest';

import { setPageTitleOverride, usePageTitle } from '../../../src/hooks/usePageTitle';
import { renderNotes } from './testUtils';

function TitleDisplay() {
  const title = usePageTitle();
  return <p>{title}</p>;
}

function Overrider({ title }: { title: string }) {
  useEffect(() => {
    setPageTitleOverride(title);
    return () => setPageTitleOverride(null);
  }, [title]);
  return null;
}

it('falls back to DISP with no staticData title and no override', async () => {
  await renderNotes(<TitleDisplay />);

  expect(screen.getByText('DISP')).toBeInTheDocument();
});

// §16.2's dynamic detail-page title, without a second effect racing __root's own.
it('reflects an active override, and reverts once it is cleared', async () => {
  const { unmount } = await renderNotes(
    <>
      <TitleDisplay />
      <Overrider title="My Note · DISP" />
    </>,
  );

  expect(await screen.findByText('My Note · DISP')).toBeInTheDocument();

  unmount();
  await renderNotes(<TitleDisplay />);
  expect(screen.getByText('DISP')).toBeInTheDocument();
});
