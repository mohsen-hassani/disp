import { http, HttpResponse } from 'msw';

import type {
  ApiTokenOut,
  AuthAcceptInviteResponse,
  AuthCreateInviteResponse,
  AuthCreateTokenResponse,
  AuthListInvitesResponse,
  AuthListTokensResponse,
  AuthLoginResponse,
  AuthMeResponse,
  AuthRefreshResponse,
  DashboardManifestResponse,
  DashboardTileResponse,
  DashboardTilesResponse,
  HealthCheckResponse,
  HealthLiveResponse,
  InviteOut,
  NoteOut,
  NotesCreateResponse,
  NotesGetResponse,
  NotesListResponse,
  NotesUpdateResponse,
  SettingsGetResponse,
  SettingsUpdateResponse,
} from '../../src/api/generated';
import {
  mockApiToken,
  mockCreateApiTokenResponse,
  mockCreateInviteResponse,
  mockHealthResponse,
  mockInvite,
  mockLiveResponse,
  mockLoginResponse,
  mockManifest,
  mockMeResponse,
  mockNote,
  mockNotesPage,
  mockTileData,
  mockTilesResponse,
} from './fixtures';

/**
 * §23.2: handlers built with `HttpResponse.json<T>()` against the exact
 * generated response types M02's SDK uses — a handler whose body doesn't
 * satisfy `T` fails `tsc`, not a test run. Every handler here returns the
 * default-happy-path fixture; a consuming test overrides one via
 * `server.use(...)` (MSW's own per-test override mechanism) rather than
 * this file growing a branch per test case.
 */
export const handlers = [
  http.get('/health', () => HttpResponse.json<HealthCheckResponse>(mockHealthResponse())),
  http.head('/health/live', () => HttpResponse.json<HealthLiveResponse>(mockLiveResponse())),

  http.post('/api/auth/login', () => HttpResponse.json<AuthLoginResponse>(mockLoginResponse())),
  http.post('/api/auth/refresh', () => HttpResponse.json<AuthRefreshResponse>(mockLoginResponse())),
  http.post('/api/auth/logout', () => new HttpResponse(null, { status: 204 })),
  http.get('/api/auth/me', () => HttpResponse.json<AuthMeResponse>(mockMeResponse())),
  http.post('/api/auth/password', () => new HttpResponse(null, { status: 204 })),
  http.post('/api/auth/accept-invite', () =>
    HttpResponse.json<AuthAcceptInviteResponse>(mockLoginResponse(), { status: 201 }),
  ),

  http.get('/api/auth/tokens', () =>
    HttpResponse.json<AuthListTokensResponse>([mockApiToken()] satisfies ApiTokenOut[]),
  ),
  http.post('/api/auth/tokens', () =>
    HttpResponse.json<AuthCreateTokenResponse>(mockCreateApiTokenResponse(), { status: 201 }),
  ),
  http.delete('/api/auth/tokens/:tokenId', () => new HttpResponse(null, { status: 204 })),

  http.get('/api/auth/invites', () =>
    HttpResponse.json<AuthListInvitesResponse>([mockInvite()] satisfies InviteOut[]),
  ),
  http.post('/api/auth/invites', () =>
    HttpResponse.json<AuthCreateInviteResponse>(mockCreateInviteResponse(), { status: 201 }),
  ),
  http.delete('/api/auth/invites/:inviteId', () => new HttpResponse(null, { status: 204 })),

  http.get('/api/dashboard/manifest', () =>
    HttpResponse.json<DashboardManifestResponse>(mockManifest()),
  ),
  http.get('/api/dashboard/tiles', () =>
    HttpResponse.json<DashboardTilesResponse>(mockTilesResponse()),
  ),
  http.get('/api/dashboard/tiles/:tileKey', ({ params }) =>
    HttpResponse.json<DashboardTileResponse>(
      mockTileData({ key: String(params.tileKey), title: String(params.tileKey) }),
    ),
  ),

  http.get('/api/settings/:domain', () => HttpResponse.json<SettingsGetResponse>({})),
  http.put('/api/settings/:domain', async ({ request }) =>
    HttpResponse.json<SettingsUpdateResponse>((await request.json()) as SettingsUpdateResponse),
  ),

  http.get('/api/notes', () => HttpResponse.json<NotesListResponse>(mockNotesPage())),
  http.post('/api/notes', async ({ request }) => {
    const body = (await request.json()) as Partial<NoteOut>;
    return HttpResponse.json<NotesCreateResponse>(mockNote(body), { status: 201 });
  }),
  http.get('/api/notes/:noteId', ({ params }) =>
    HttpResponse.json<NotesGetResponse>(mockNote({ id: String(params.noteId) })),
  ),
  http.patch('/api/notes/:noteId', async ({ params, request }) => {
    const body = (await request.json()) as Partial<NoteOut>;
    return HttpResponse.json<NotesUpdateResponse>(mockNote({ id: String(params.noteId), ...body }));
  }),
  http.delete('/api/notes/:noteId', () => new HttpResponse(null, { status: 204 })),
  http.post('/api/notes/:noteId/share', () => new HttpResponse(null, { status: 204 })),
];
