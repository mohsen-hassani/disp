import type { UserOut } from '../../../src/api/generated';

export const TEST_USER: UserOut = {
  id: 'user-1',
  email: 'test@example.com',
  display_name: 'Test User',
  is_admin: false,
};

export function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

export function loginResponse(
  overrides: Partial<{ access_token: string; expires_in: number; user: UserOut }> = {},
): Response {
  return jsonResponse({
    access_token: overrides.access_token ?? 'test-access-token',
    token_type: 'bearer',
    expires_in: overrides.expires_in ?? 300,
    user: overrides.user ?? TEST_USER,
  });
}

export function meResponse(user: UserOut = TEST_USER): Response {
  return jsonResponse({ ...user, auth_method: 'password' });
}

export function problemResponse(
  status: number,
  code: string,
  extra: Partial<{ detail: string; headers: Record<string, string> }> = {},
): Response {
  const { detail, headers } = extra;
  return jsonResponse(
    {
      type: 'about:blank',
      title: code,
      status,
      detail: detail ?? code,
      instance: '/api/whatever',
      code,
      request_id: 'req-test',
    },
    { status, headers: { 'Content-Type': 'application/json', ...headers } },
  );
}

/** Every generated SDK call goes through a Request whose URL Node's undici
 * requires to be absolute (unlike a real browser resolving against
 * document.location — see M02's client.test.ts for the full explanation).
 * Tests that exercise the real client must set this before running. */
export function pathnameOf(request: Request): string {
  return new URL(request.url).pathname;
}
