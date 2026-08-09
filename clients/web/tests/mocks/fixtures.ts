// §23.2: default response bodies for tests/mocks/handlers.ts, typed against
// the same generated types M02's SDK uses — a fixture here that drifts from
// the real API shape is a compile error, not a runtime surprise a test only
// discovers by failing confusingly later.
import type {
  ApiTokenOut,
  CalendarEntry,
  CalendarOut,
  CareIntervalOut,
  CareLogOut,
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
  PagePlantOut,
  PlantDetailOut,
  PlantOut,
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
        // §12.2: nav entries and tile deep links are manifest-driven, so a
        // module with screens must declare this or the client correctly
        // treats it as dashboard-only — matching what the real backend sends.
        client_nav: { label: 'Notes', icon: 'sticky-note', order: 10, routes: ['', '{note_id}'] },
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

export function mockPlant(overrides: Partial<PlantOut> = {}): PlantOut {
  return {
    id: 'plant-1',
    name: 'Monstera',
    description: null,
    care_notes: null,
    has_image: false,
    image_url: null,
    due_count: 0,
    max_days_overdue: 0,
    next_due_on: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

export function mockCareInterval(overrides: Partial<CareIntervalOut> = {}): CareIntervalOut {
  return {
    id: 'interval-1',
    plant_id: 'plant-1',
    name: 'Water',
    interval_days: 7,
    next_due_on: '2026-01-08',
    last_done_on: '2026-01-01',
    active: true,
    days_overdue: -7,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

export function mockPlantDetail(overrides: Partial<PlantDetailOut> = {}): PlantDetailOut {
  return { ...mockPlant(), intervals: [mockCareInterval()], ...overrides };
}

export function mockPlantsPage(overrides: Partial<PagePlantOut> = {}): PagePlantOut {
  return { items: [mockPlant()], next_cursor: null, has_more: false, ...overrides };
}

export function mockCareLog(overrides: Partial<CareLogOut> = {}): CareLogOut {
  return {
    id: 'log-1',
    plant_id: 'plant-1',
    interval_id: 'interval-1',
    action_name: 'Water',
    due_on: '2026-01-01',
    completed_on: '2026-01-01',
    days_late: 0,
    note: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

export function mockCalendarEntry(overrides: Partial<CalendarEntry> = {}): CalendarEntry {
  return {
    day: '2026-01-05',
    kind: 'due',
    plant_id: 'plant-1',
    plant_name: 'Monstera',
    interval_id: 'interval-1',
    action_name: 'Water',
    ...overrides,
  };
}

export function mockCalendarOut(overrides: Partial<CalendarOut> = {}): CalendarOut {
  return {
    month: '2026-01',
    start: '2026-01-01',
    end: '2026-01-31',
    entries: [mockCalendarEntry()],
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
