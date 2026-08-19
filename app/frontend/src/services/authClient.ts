const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

const ACCESS_TOKEN_KEY = 'medicore:accessToken';
const CURRENT_USER_KEY = 'medicore:currentUser';

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

function storeAuth(response: AuthResponse): AuthUser {
  localStorage.setItem(ACCESS_TOKEN_KEY, response.access_token);
  localStorage.setItem(CURRENT_USER_KEY, JSON.stringify(response.user));

  return response.user;
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
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
  return Boolean(getAccessToken());
}

export function logout(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(CURRENT_USER_KEY);
  localStorage.removeItem('medicore:lastAnalysisRunId');
  localStorage.removeItem('medicore:lastLabReportId');
}

export async function login(
  nickname: string,
  password: string,
  accountType: AccountType,
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

  return storeAuth((await response.json()) as AuthResponse);
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
