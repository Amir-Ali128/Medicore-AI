const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

const LEGACY_ACCESS_TOKEN_KEY = 'medicore:accessToken';
const LEGACY_CURRENT_USER_KEY = 'medicore:currentUser';
const ADMIN_ACCESS_TOKEN_KEY = 'medicore:adminAccessToken';
const ADMIN_CURRENT_USER_KEY = 'medicore:adminCurrentUser';
const CLINICAL_ACCESS_TOKEN_KEY = 'medicore:clinicalAccessToken';
const CLINICAL_CURRENT_USER_KEY = 'medicore:clinicalCurrentUser';
const MEDICORE_STORAGE_PREFIX = 'medicore:';

export type UserRole =
  | 'admin'
  | 'doctor'
  | 'patient'
  | 'lab_staff'
  | 'viewer'
  | 'system';
export type AccountType = 'individual' | 'institutional';
export type SessionWorkspace = 'admin' | 'clinical';

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
      if (typeof body?.detail === 'string') return body.detail;
      return JSON.stringify(body?.detail ?? body);
    } catch {
      return response.statusText;
    }
  }

  return response.text();
}

function workspaceFromLocation(): SessionWorkspace {
  return window.location.hash.startsWith('#/admin') ? 'admin' : 'clinical';
}

function tokenKey(workspace: SessionWorkspace) {
  return workspace === 'admin' ? ADMIN_ACCESS_TOKEN_KEY : CLINICAL_ACCESS_TOKEN_KEY;
}

function userKey(workspace: SessionWorkspace) {
  return workspace === 'admin' ? ADMIN_CURRENT_USER_KEY : CLINICAL_CURRENT_USER_KEY;
}

function readUserAtKey(key: string): AuthUser | null {
  const raw = localStorage.getItem(key);
  if (!raw) return null;

  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    localStorage.removeItem(key);
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
    value === 'viewer' ||
    value === 'system'
  );
}

function isJwtExpiredOrInvalid(token: string): boolean {
  const payload = readJwtPayload(token);
  if (!payload || typeof payload.exp !== 'number') return true;
  return payload.exp * 1000 <= Date.now();
}

function isRoleForWorkspace(role: UserRole, workspace: SessionWorkspace) {
  return workspace === 'admin' ? role === 'admin' : role !== 'admin';
}

function removeLegacyAuth() {
  localStorage.removeItem(LEGACY_ACCESS_TOKEN_KEY);
  localStorage.removeItem(LEGACY_CURRENT_USER_KEY);
}

function migrateLegacySession(workspace: SessionWorkspace): void {
  if (localStorage.getItem(tokenKey(workspace))) return;

  const legacyToken = localStorage.getItem(LEGACY_ACCESS_TOKEN_KEY);
  const legacyUser = readUserAtKey(LEGACY_CURRENT_USER_KEY);
  if (!legacyToken || !legacyUser || isJwtExpiredOrInvalid(legacyToken)) return;
  if (!isRoleForWorkspace(legacyUser.role, workspace)) return;

  localStorage.setItem(tokenKey(workspace), legacyToken);
  localStorage.setItem(userKey(workspace), JSON.stringify(legacyUser));
  removeLegacyAuth();
}

function clearAdminSession(): void {
  localStorage.removeItem(ADMIN_ACCESS_TOKEN_KEY);
  localStorage.removeItem(ADMIN_CURRENT_USER_KEY);
}

function clearClinicalWorkspace(): void {
  const keysToRemove: string[] = [];

  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index);
    if (!key?.startsWith(MEDICORE_STORAGE_PREFIX)) continue;
    if (key === ADMIN_ACCESS_TOKEN_KEY || key === ADMIN_CURRENT_USER_KEY) continue;
    keysToRemove.push(key);
  }

  keysToRemove.forEach((key) => localStorage.removeItem(key));
}

function clearWorkspace(workspace: SessionWorkspace): void {
  if (workspace === 'admin') {
    clearAdminSession();
    return;
  }
  clearClinicalWorkspace();
}

function storeAuth(response: AuthResponse): AuthUser {
  const workspace: SessionWorkspace = response.user.role === 'admin' ? 'admin' : 'clinical';
  const previousUser = readUserAtKey(userKey(workspace));

  if (!previousUser || previousUser.id !== response.user.id) {
    clearWorkspace(workspace);
  }

  localStorage.setItem(tokenKey(workspace), response.access_token);
  localStorage.setItem(userKey(workspace), JSON.stringify(response.user));
  removeLegacyAuth();
  return response.user;
}

export function getAccessToken(
  workspace: SessionWorkspace = workspaceFromLocation(),
): string | null {
  migrateLegacySession(workspace);
  return localStorage.getItem(tokenKey(workspace));
}

export function clearAccessToken(
  workspace: SessionWorkspace = workspaceFromLocation(),
): void {
  localStorage.removeItem(tokenKey(workspace));
}

export function getCurrentUser(
  workspace: SessionWorkspace = workspaceFromLocation(),
): AuthUser | null {
  migrateLegacySession(workspace);
  return readUserAtKey(userKey(workspace));
}

export function getStoredUser(
  workspace: SessionWorkspace = workspaceFromLocation(),
): AuthUser | null {
  return getCurrentUser(workspace);
}

export function getAuthenticatedRole(
  workspace: SessionWorkspace = workspaceFromLocation(),
): UserRole | null {
  const token = getAccessToken(workspace);
  if (!token || isJwtExpiredOrInvalid(token)) return null;

  const role = readJwtPayload(token)?.role;
  if (isKnownRole(role) && isRoleForWorkspace(role, workspace)) return role;

  const storedRole = getStoredUser(workspace)?.role;
  return isKnownRole(storedRole) && isRoleForWorkspace(storedRole, workspace)
    ? storedRole
    : null;
}

export function isAuthenticated(
  workspace: SessionWorkspace = workspaceFromLocation(),
): boolean {
  const token = getAccessToken(workspace);
  if (!token) return false;

  if (isJwtExpiredOrInvalid(token)) {
    clearWorkspace(workspace);
    return false;
  }

  return getAuthenticatedRole(workspace) !== null;
}

export function logout(
  workspace: SessionWorkspace = workspaceFromLocation(),
): void {
  clearWorkspace(workspace);
}

export async function login(
  nickname: string,
  password: string,
  accountType: AccountType,
  options: LoginOptions = {},
): Promise<AuthUser> {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
    throw new Error('Bu hesap yönetici hesabıdır. Yönetici girişini kullanın.');
  }

  return storeAuth(auth);
}

export async function register(
  payload: RegisterPayload,
): Promise<AuthUser> {
  const response = await fetch(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new Error(message || 'Hesap oluşturulamadı.');
  }

  return storeAuth((await response.json()) as AuthResponse);
}
