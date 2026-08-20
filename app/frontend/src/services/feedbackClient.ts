import { getAccessToken } from './authClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  import.meta.env.VITE_MEDICORE_API_BASE_URL ??
  'http://127.0.0.1:8000';

export type FeedbackCategory = 'suggestion' | 'bug' | 'usability' | 'other';
export type FeedbackStatus = 'new' | 'read' | 'resolved';

export type FeedbackItem = {
  id: string;
  user_id: string | null;
  nickname: string | null;
  category: FeedbackCategory;
  subject: string;
  message: string;
  status: FeedbackStatus;
  created_at: string;
  updated_at: string;
};

async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getAccessToken();
  if (!token) throw new Error('Oturum bulunamadı.');

  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  headers.set('Authorization', `Bearer ${token}`);
  if (init.body) headers.set('Content-Type', 'application/json');

  return fetch(`${API_BASE_URL.replace(/\/$/, '')}${path}`, { ...init, headers });
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? body);
  } catch {
    return response.statusText || 'İstek başarısız oldu.';
  }
}

export async function submitFeedback(payload: {
  category: FeedbackCategory;
  subject: string;
  message: string;
}): Promise<FeedbackItem> {
  const response = await authFetch('/feedback', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<FeedbackItem>;
}

export async function getMyFeedback(): Promise<FeedbackItem[]> {
  const response = await authFetch('/feedback/mine');
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<FeedbackItem[]>;
}

export async function getAdminFeedback(): Promise<FeedbackItem[]> {
  const response = await authFetch('/feedback/admin?limit=200');
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<FeedbackItem[]>;
}

export async function setFeedbackStatus(
  id: string,
  status: FeedbackStatus,
): Promise<FeedbackItem> {
  const response = await authFetch(`/feedback/admin/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<FeedbackItem>;
}
