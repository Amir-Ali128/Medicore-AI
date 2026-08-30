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

function isJwtExpiredOrInvalid(token: string): boolean {
  try {
    const parts = token.split('.');
    if (parts.length !== 3 || !parts[1]) return true;

    const normalized = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
    const payload = JSON.parse(atob(padded)) as { exp?: number };

    if (typeof payload.exp !== 'number') return true;
    return payload.exp * 1000 <= Date.now();
  } catch {
    return true;
  }
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

  // A fresh login with no valid stored user may still have stale patient data
  // from an older build/session. A different account must always start clean.
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
  // Preserve the current user's local clinical workspace so the same user can
  // sign in again without losing unsaved browser-side context. A different user
  // is still protected by storeAuth(), which clears the full MediCore state.
  localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export function getCurrentUser(): AuthUser | null {
  const raw = localStorage.getItem(CURRENT_USER_KEY);

  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    localStorage.removeItem(CURRENT_USER_KEY);
    return null;
  }
}

// Backward-compatible alias for existing components such as Topbar.tsx
export function getStoredUser(): AuthUser | null {
  return getCurrentUser();
}

export function isAuthenticated(): boolean {
  const token = getAccessToken();
  if (!token) return false;

  if (isJwtExpiredOrInvalid(token)) {
    clearAccessToken();
    return false;
  }

  return true;
}

export function logout(): void {
  // Health/clinical data must not survive into the next account on a shared
  // browser. This also clears the token and current-user values.
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

  // Admin authentication has a dedicated entry point. The regular individual /
  // institutional login must never silently turn into an admin session.
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
