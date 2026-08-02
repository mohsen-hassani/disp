import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

import { client } from '../../../src/api/client';
import { AddIntervalForm } from '../../../src/components/plants/AddIntervalForm';
import { CalendarLegend, CareCalendar } from '../../../src/components/plants/CareCalendar';
import { CareIntervalList } from '../../../src/components/plants/CareIntervalList';
import { CreatePlantDialog } from '../../../src/components/plants/CreatePlantDialog';
import { PlantCard } from '../../../src/components/plants/PlantCard';
import { PlantPhoto } from '../../../src/components/plants/PlantPhoto';
import { jsonResponse } from '../auth/testUtils';
import { calendarEntry, interval, plant, plantDetail, renderPlants } from './testUtils';

beforeAll(() => {
  client.setConfig({ baseUrl: 'http://localhost' });
});
afterAll(() => {
  client.setConfig({ baseUrl: '' });
});

let fetchSpy: ReturnType<typeof vi.spyOn>;
afterEach(() => {
  fetchSpy?.mockRestore();
});

function noop(): void {
  // callback the test doesn't assert on
}

/**
 * `src/api/client.ts` builds a `Request` and calls `fetch(request)` with a
 * single argument, so there is no `RequestInit` in `mock.calls[0][1]` — the
 * method and headers live on the Request itself.
 */
function requestOf(spy: ReturnType<typeof vi.spyOn>): Request {
  return spy.mock.calls[0][0] as Request;
}

// --------------------------------------------------------------------------
// PlantCard
// --------------------------------------------------------------------------

it('badges a plant that has work outstanding', async () => {
  await renderPlants(
    <PlantCard plant={plant({ due_count: 2, max_days_overdue: 3, next_due_on: '2026-02-27' })} />,
  );
  expect(screen.getByText(/2 due/)).toBeInTheDocument();
  expect(screen.getByText(/3d behind/)).toBeInTheDocument();
});

it('shows the next date instead of a badge when nothing is due', async () => {
  await renderPlants(<PlantCard plant={plant({ due_count: 0, next_due_on: '2026-03-18' })} />);
  expect(screen.getByText(/^Next /)).toBeInTheDocument();
  expect(screen.queryByText(/due$/)).not.toBeInTheDocument();
});

it('says so when a plant has no schedule at all', async () => {
  await renderPlants(<PlantCard plant={plant({ next_due_on: null })} />);
  expect(screen.getByText('No schedule')).toBeInTheDocument();
});

it('renders the photo when the plant has one', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(new Blob(['x'], { type: 'image/png' })));

  const { container } = await renderPlants(
    <PlantCard plant={plant({ has_image: true, image_url: '/api/plants/plant-1/image' })} />,
  );
  // The photo route is bearer-gated (§12), so the image is fetched through
  // the authenticated client and rendered from a blob URL, not the raw
  // `image_url` a plain <img src> could never authenticate against.
  await waitFor(() =>
    expect(container.querySelector('img')?.getAttribute('src')).toMatch(/^blob:/),
  );
  // The thumbnail carries alt="" on purpose — the plant's name is right next
  // to it, so announcing the image too would just be duplication.
  expect(container.querySelector('img')).toHaveAttribute('alt', '');
});

// --------------------------------------------------------------------------
// CareIntervalList
// --------------------------------------------------------------------------

it('prompts for a first interval when the schedule is empty', async () => {
  await renderPlants(<CareIntervalList plantId="plant-1" intervals={[]} offline={false} />);
  expect(screen.getByText(/No intervals yet/)).toBeInTheDocument();
});

it('shows each interval with its cadence and due state', async () => {
  await renderPlants(
    <CareIntervalList
      plantId="plant-1"
      intervals={[
        interval({ id: 'i1', name: 'Water', days_overdue: 2 }),
        interval({ id: 'i2', name: 'Green Fertilizer', interval_days: 30, days_overdue: 0 }),
      ]}
      offline={false}
    />,
  );
  expect(screen.getByText('Water')).toBeInTheDocument();
  expect(screen.getByText('2 days behind')).toBeInTheDocument();
  expect(screen.getByText('Due today')).toBeInTheDocument();
  expect(screen.getByText(/Every 30 days/)).toBeInTheDocument();
});

it('distinguishes an interval that has never been completed', async () => {
  await renderPlants(
    <CareIntervalList
      plantId="plant-1"
      intervals={[interval({ last_done_on: null })]}
      offline={false}
    />,
  );
  expect(screen.getByText(/never done/)).toBeInTheDocument();
});

it('marks an action done and reports the next date the server chose', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    jsonResponse(
      {
        log: {
          id: 'log-1',
          plant_id: 'plant-1',
          interval_id: 'i1',
          action_name: 'Water',
          due_on: '2026-03-01',
          completed_on: '2026-03-03',
          days_late: 2,
          note: null,
          created_at: '2026-03-03T00:00:00Z',
        },
        interval: interval({ id: 'i1', next_due_on: '2026-03-18' }),
      },
      { status: 201 },
    ),
  );

  await renderPlants(
    <CareIntervalList
      plantId="plant-1"
      intervals={[interval({ id: 'i1', days_overdue: 2 })]}
      offline={false}
    />,
  );
  await userEvent.click(screen.getByRole('button', { name: /Mark done/ }));

  // The toast quotes the server's recomputed date, not a client guess.
  await waitFor(() => expect(screen.getByText(/next on 2026-03-18/)).toBeInTheDocument());
  expect(requestOf(fetchSpy).method).toBe('POST');
});

it('surfaces the server error when marking done fails', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    jsonResponse(
      {
        type: 'about:blank',
        title: 'Forbidden',
        status: 403,
        detail: 'You do not have permission to perform this action.',
        instance: '/api/plants/plant-1',
        code: 'acl.forbidden',
        request_id: 'req-1',
      },
      { status: 403 },
    ),
  );

  await renderPlants(
    <CareIntervalList plantId="plant-1" intervals={[interval()]} offline={false} />,
  );
  await userEvent.click(screen.getByRole('button', { name: /Mark done/ }));
  await waitFor(() => expect(screen.getByText(/do not have permission/)).toBeInTheDocument());
});

it('asks for confirmation before deleting an interval', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(null, { status: 204 }));

  await renderPlants(
    <CareIntervalList
      plantId="plant-1"
      intervals={[interval({ name: 'Water' })]}
      offline={false}
    />,
  );

  await userEvent.click(screen.getByRole('button', { name: 'Delete Water' }));
  expect(screen.getByText('Delete this interval?')).toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: 'Delete' }));
  await waitFor(() => expect(screen.getByText('Water removed')).toBeInTheDocument());
});

it('lets the confirmation be backed out of without deleting', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch');
  await renderPlants(
    <CareIntervalList plantId="plant-1" intervals={[interval()]} offline={false} />,
  );

  await userEvent.click(screen.getByRole('button', { name: 'Delete Water' }));
  await userEvent.click(screen.getByRole('button', { name: 'Keep' }));

  expect(screen.queryByText('Delete this interval?')).not.toBeInTheDocument();
  expect(fetchSpy).not.toHaveBeenCalled();
});

it('disables mutating controls while offline', async () => {
  await renderPlants(
    <CareIntervalList plantId="plant-1" intervals={[interval()]} offline={true} />,
  );
  expect(screen.getByRole('button', { name: /Mark done/ })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Delete Water' })).toBeDisabled();
});

// --------------------------------------------------------------------------
// AddIntervalForm
// --------------------------------------------------------------------------

it('defaults to a 15-day cadence anchored to today', async () => {
  await renderPlants(<AddIntervalForm plantId="plant-1" offline={false} />);
  expect(screen.getByLabelText('Every (days)')).toHaveValue(15);
  // Not in the future — the server rejects a future last_done_on.
  expect(screen.getByLabelText('Last done')).toHaveAttribute('max');
});

it('submits a new interval and clears itself', async () => {
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    jsonResponse(interval({ name: 'Green Fertilizer', next_due_on: '2026-04-01' }), {
      status: 201,
    }),
  );

  await renderPlants(<AddIntervalForm plantId="plant-1" offline={false} />);
  await userEvent.type(screen.getByLabelText('Action'), 'Green Fertilizer');
  await userEvent.clear(screen.getByLabelText('Every (days)'));
  await userEvent.type(screen.getByLabelText('Every (days)'), '30');
  await userEvent.click(screen.getByRole('button', { name: /Add interval/ }));

  await waitFor(() =>
    expect(screen.getByText(/Green Fertilizer scheduled for 2026-04-01/)).toBeInTheDocument(),
  );
  expect(screen.getByLabelText('Action')).toHaveValue('');
});

it('will not submit without an action name', async () => {
  await renderPlants(<AddIntervalForm plantId="plant-1" offline={false} />);
  expect(screen.getByRole('button', { name: /Add interval/ })).toBeDisabled();
});

// --------------------------------------------------------------------------
// CreatePlantDialog
// --------------------------------------------------------------------------

it('creates a plant from a name alone and hands back its id', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(jsonResponse(plant({ id: 'new-plant' }), { status: 201 }));
  const onCreated = vi.fn();

  await renderPlants(<CreatePlantDialog open onOpenChange={noop} onCreated={onCreated} />);
  await userEvent.type(screen.getByLabelText('Name'), 'Sansevieria');
  await userEvent.click(screen.getByRole('button', { name: 'Create plant' }));

  await waitFor(() => expect(onCreated).toHaveBeenCalledWith('new-plant'));
});

it('keeps the create button disabled until a name is typed', async () => {
  await renderPlants(<CreatePlantDialog open onOpenChange={noop} onCreated={noop} />);
  expect(screen.getByRole('button', { name: 'Create plant' })).toBeDisabled();
});

// --------------------------------------------------------------------------
// PlantPhoto
// --------------------------------------------------------------------------

it('offers to add a photo when there is none, and shows no remove button', async () => {
  await renderPlants(<PlantPhoto plant={plantDetail()} offline={false} />);
  expect(screen.getByRole('button', { name: /Add photo/ })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Remove/ })).not.toBeInTheDocument();
});

it('fetches the photo through the authenticated client and renders it from a blob URL', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(new Blob(['x'], { type: 'image/png' })));

  await renderPlants(
    <PlantPhoto
      plant={plantDetail({
        has_image: true,
        image_url: '/api/plants/plant-1/image',
        updated_at: '2026-03-03T10:00:00Z',
      })}
      offline={false}
    />,
  );
  // The route is bearer-gated (§12) with no cookie fallback, so a bare
  // <img src> pointed at `image_url` could never authenticate — the bytes
  // must come from an authenticated fetch, exposed as an object URL.
  await waitFor(() => expect(screen.getByRole('img').getAttribute('src')).toMatch(/^blob:/));
  expect(requestOf(fetchSpy).url).toContain('/api/plants/plant-1/image');
  expect(screen.getByRole('button', { name: /Replace photo/ })).toBeInTheDocument();
});

it('uploads a chosen file as multipart', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(jsonResponse(plant({ has_image: true })));

  const { container } = await renderPlants(<PlantPhoto plant={plantDetail()} offline={false} />);
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  await userEvent.upload(input, new File(['x'], 'leaf.png', { type: 'image/png' }));

  await waitFor(() => expect(screen.getByText('Photo updated')).toBeInTheDocument());
  const request = requestOf(fetchSpy);
  expect(request.method).toBe('PUT');
  // Multipart, not JSON — the browser sets the boundary itself, so the
  // client must not have forced a Content-Type header.
  expect(request.headers.get('content-type')).not.toBe('application/json');
});

it('removes an existing photo', async () => {
  fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    // First call is the mount-time photo fetch (`usePlantImageUrl`), second
    // is the delete mutation.
    .mockResolvedValueOnce(new Response(new Blob(['x'], { type: 'image/png' })))
    .mockResolvedValueOnce(new Response(null, { status: 204 }));

  await renderPlants(
    <PlantPhoto
      plant={plantDetail({ has_image: true, image_url: '/api/plants/plant-1/image' })}
      offline={false}
    />,
  );
  await waitFor(() => expect(screen.getByRole('img').getAttribute('src')).toMatch(/^blob:/));
  await userEvent.click(screen.getByRole('button', { name: /Remove/ }));
  await waitFor(() => expect(screen.getByText('Photo removed')).toBeInTheDocument());
});

// --------------------------------------------------------------------------
// CareCalendar
// --------------------------------------------------------------------------

it('places entries on their own day and labels the kind for screen readers', async () => {
  await renderPlants(
    <CareCalendar
      month="2026-03"
      entries={[
        calendarEntry({ day: '2026-03-03', kind: 'done', action_name: 'Water' }),
        calendarEntry({ day: '2026-03-18', kind: 'due', action_name: 'Feed' }),
      ]}
    />,
  );
  expect(screen.getByTitle(/Water — Sansevieria \(done\)/)).toBeInTheDocument();
  expect(screen.getByTitle(/Feed — Sansevieria \(due\)/)).toBeInTheDocument();
});

it('truncates a busy day and says how many are hidden', async () => {
  const entries = ['a', 'b', 'c', 'd', 'e'].map((id) =>
    calendarEntry({ day: '2026-03-10', interval_id: id, action_name: `Action ${id}` }),
  );
  await renderPlants(<CareCalendar month="2026-03" entries={entries} />);
  expect(screen.getByText('+2 more')).toBeInTheDocument();
});

it('renders a full six-week grid even with no entries', async () => {
  const { container } = await renderPlants(<CareCalendar month="2026-03" entries={[]} />);
  // 7 weekday headers + 42 day cells.
  expect(container.querySelectorAll('.grid > *')).toHaveLength(49);
});

it('names every entry kind in the legend', async () => {
  await renderPlants(<CalendarLegend />);
  for (const label of ['done', 'overdue', 'due', 'projected']) {
    expect(screen.getByText(label)).toBeInTheDocument();
  }
});

it('marks today inside the current month', async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 2, 18, 12, 0, 0));
  try {
    await renderPlants(<CareCalendar month="2026-03" entries={[]} />);
    expect(screen.getByText('today')).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

it('scopes a day cell to the entries for that day only', async () => {
  const { container } = await renderPlants(
    <CareCalendar
      month="2026-03"
      entries={[calendarEntry({ day: '2026-03-05', action_name: 'Only this' })]}
    />,
  );
  const cells = Array.from(container.querySelectorAll('.grid > div'));
  const withEntries = cells.filter((cell) => within(cell as HTMLElement).queryByTitle(/Only this/));
  expect(withEntries).toHaveLength(1);
});
