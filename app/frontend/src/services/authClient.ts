const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

const ACCESS_TOKEN_KEY = 'medicore:accessToken';
const CURRENT_USER_KEY = 'medicore:currentUser';
const MEDICORE_STORAGE_PREFIX = 'medicore:';

export type UserRole = 'admin' | 'doctor' | 'patient' | 'lab_staff' | 'system';
export type AccountType = 'individual' | 'institutional';

export type AuthUser = {
  id: string;
  nickname: string;
  role: UserRole;
  is_active: boolean;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export type RegisterPayload = {
  nickname: string;
  password: string;
};

type LoginOptions = {
  allowAdmin?: boolean;
};

type JwtPayload = {
  exp?: number;
  role?: string;
};

async function readErrorMessage(response: Response): Promise<string> {
  const contentType = response.headers.get('content-type') ?? '';

  if (contentType.includes('application/json')) {
    try {
      const body = await response.json();

      if (typeof body?.detail === 'string') {
        return body.detail;
      }

      return JSON.stringify(body?.detail ?? body);
    } catch {
      return response.statusText;
    }
  }

  return response.text();
}

function readStoredUserUnsafe(): AuthUser | null {
  const raw = localStorage.getItem(CURRENT_USER_KEY);
  if (!raw) return null;

  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

function readJwtPayload(token: string): JwtPayload | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3 || !parts[1]) return null;

    const normalized = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
    return JSON.parse(atob(padded)) as JwtPayload;
  } catch {
    return null;
  }
}

function isKnownRole(value: unknown): value is UserRole {
  return (
    value === 'admin' ||
    value === 'doctor' ||
    value === 'patient' ||
    value === 'lab_staff' ||
    value === 'system'
  );
}

function isJwtExpiredOrInvalid(token: string): boolean {
  const payload = readJwtPayload(token);
  if (!payload || typeof payload.exp !== 'number') return true;
  return payload.exp * 1000 <= Date.now();
}

/**
 * Remove every client-side MediCore value from this browser profile.
 *
 * Patient forms, active patient ids, report ids, local archive snapshots and auth
 * data all use the `medicore:` prefix. Clearing the complete prefix is deliberate:
 * a different account must never inherit health information left in localStorage
 * by the previous account on the same browser.
 */
function clearMediCoreLocalState(): void {
  const keysToRemove: string[] = [];

  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index);
    if (key?.startsWith(MEDICORE_STORAGE_PREFIX)) {
      keysToRemove.push(key);
    }
  }

  keysToRemove.forEach((key) => localStorage.removeItem(key));
}

function storeAuth(response: AuthResponse): AuthUser {
  const previousUser = readStoredUserUnsafe();

  if (!previousUser || previousUser.id !== response.user.id) {
    clearMediCoreLocalState();
  }

  localStorage.setItem(ACCESS_TOKEN_KEY, response.access_token);
  localStorage.setItem(CURRENT_USER_KEY, JSON.stringify(response.user));

  return response.user;
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function clearAccessToken(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export function getCurrentUser(): AuthUser | null {
  const raw = localStorage.getItem(CURRENT_USER_KEY);

  if (!raw) return null;

  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    localStorage.removeItem(CURRENT_USER_KEY);
    return null;
  }
}

export function getStoredUser(): AuthUser | null {
  return getCurrentUser();
}

/**
 * Read the authenticated role from the signed JWT payload first. This keeps the
 * admin/clinical workspace stable across a hard refresh even if the cached user
 * object is unavailable during the first render.
 */
export function getAuthenticatedRole(): UserRole | null {
  const token = getAccessToken();
  if (!token || isJwtExpiredOrInvalid(token)) return null;

  const role = readJwtPayload(token)?.role;
  if (isKnownRole(role)) return role;

  const storedRole = getStoredUser()?.role;
  return isKnownRole(storedRole) ? storedRole : null;
}

export function isAuthenticated(): boolean {
  const token = getAccessToken();
  if (!token) return false;

  if (isJwtExpiredOrInvalid(token)) {
    clearAccessToken();
    return false;
  }

  return getAuthenticatedRole() !== null;
}

export function logout(): void {
  clearMediCoreLocalState();
}

export async function login(
  nickname: string,
  password: string,
  accountType: AccountType,
  options: LoginOptions = {},
): Promise<AuthUser> {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      nickname,
      password,
      account_type: accountType,
    }),
  });

  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new Error(message || 'Giriş yapılamadı.');
  }

  const auth = (await response.json()) as AuthResponse;

  if (auth.user.role === 'admin' && options.allowAdmin !== true) {
    clearMediCoreLocalState();
    throw new Error('Bu hesap yönetici hesabıdır. Yönetici girişini kullanın.');
  }

  return storeAuth(auth);
}

export async function register(
  payload: RegisterPayload,
): Promise<AuthUser> {
  const response = await fetch(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new Error(message || 'Hesap oluşturulamadı.');
  }

  return storeAuth((await response.json()) as AuthResponse);
}
