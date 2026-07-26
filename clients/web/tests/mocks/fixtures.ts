// §23.2: default response bodies for tests/mocks/handlers.ts, typed against
// the same generated types M02's SDK uses — a fixture here that drifts from
// the real API shape is a compile error, not a runtime surprise a test only
// discovers by failing confusingly later.
import type {
  ApiTokenOut,
  CreateApiTokenResponse,
  CreateInviteResponse,
  DashboardManifestResponse,
  HealthResponse,
  InviteOut,
  LiveResponse,
  LoginResponse,
  MeResponse,
  NoteOut,
  PageNoteOut,
  TileData,
  TileSpec,
  TilesResponse,
  UserOut,
} from '../../src/api/generated';

export const mockUser: UserOut = {
  id: 'user-1',
  email: 'test@example.com',
  display_name: 'Test User',
  is_admin: false,
};

export function mockMeResponse(overrides: Partial<MeResponse> = {}): MeResponse {
  return { ...mockUser, auth_method: 'password', ...overrides };
}

export function mockLoginResponse(overrides: Partial<LoginResponse> = {}): LoginResponse {
  return {
    access_token: 'mock-access-token',
    token_type: 'bearer',
    expires_in: 300,
    user: mockUser,
    ...overrides,
  };
}

export function mockNote(overrides: Partial<NoteOut> = {}): NoteOut {
  return {
    id: 'note-1',
    title: 'First note',
    body: 'Note body.',
    pinned: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

export function mockNotesPage(overrides: Partial<PageNoteOut> = {}): PageNoteOut {
  return { items: [mockNote()], next_cursor: null, has_more: false, ...overrides };
}

export function mockTileSpec(overrides: Partial<TileSpec> = {}): TileSpec {
  return { key: 'notes.recent', title: 'Recent notes', size: 'medium', order: 0, ...overrides };
}

export function mockTileData(overrides: Partial<TileData> = {}): TileData {
  return {
    key: 'notes.recent',
    title: 'Recent notes',
    generated_at: '2026-01-01T00:00:00Z',
    items: [],
    ...overrides,
  };
}

export function mockTilesResponse(tiles: TileData[] = [mockTileData()]): TilesResponse {
  return { tiles };
}

export function mockManifest(
  overrides: Partial<DashboardManifestResponse> = {},
): DashboardManifestResponse {
  return {
    platform_version: '0.1.0',
    modules: [
      {
        domain: 'notes',
        name: 'Notes',
        version: '1.0.0',
        description: null,
        tiles: [mockTileSpec()],
        notification_types: [],
        settings_panels: [],
      },
    ],
    ...overrides,
  };
}

export function mockApiToken(overrides: Partial<ApiTokenOut> = {}): ApiTokenOut {
  return {
    id: 'token-1',
    name: 'CLI',
    token_prefix: 'disp_ab12',
    created_at: '2026-01-01T00:00:00Z',
    last_used_at: null,
    expires_at: null,
    ...overrides,
  };
}

export function mockCreateApiTokenResponse(
  overrides: Partial<CreateApiTokenResponse> = {},
): CreateApiTokenResponse {
  return { ...mockApiToken(), token: 'disp_ab12cd34ef56', ...overrides };
}

export function mockInvite(overrides: Partial<InviteOut> = {}): InviteOut {
  return {
    id: 'invite-1',
    email: 'newuser@example.com',
    is_admin: false,
    expires_at: '2026-02-01T00:00:00Z',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

export function mockCreateInviteResponse(
  overrides: Partial<CreateInviteResponse> = {},
): CreateInviteResponse {
  return {
    id: 'invite-1',
    email: 'newuser@example.com',
    token: 'invite-token',
    accept_url: 'https://example.com/accept-invite?token=invite-token',
    expires_at: '2026-02-01T00:00:00Z',
    ...overrides,
  };
}

export function mockHealthResponse(overrides: Partial<HealthResponse> = {}): HealthResponse {
  return {
    status: 'ok',
    version: '0.1.0',
    database: 'ok',
    modules: ['notes'],
    worker_last_seen: null,
    ...overrides,
  };
}

export function mockLiveResponse(overrides: Partial<LiveResponse> = {}): LiveResponse {
  return { status: 'ok', ...overrides };
}
