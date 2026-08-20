import { getAccessToken } from './authClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  import.meta.env.VITE_MEDICORE_API_BASE_URL ??
  'http://127.0.0.1:8000';

export type AnalyticsSession = {
  visitor_id: string;
  user_id: string | null;
  nickname: string | null;
  role: string | null;
  first_seen_at: string;
  last_seen_at: string;
  last_path: string | null;
  ip_address: string | null;
  country_code: string | null;
  country: string | null;
  region: string | null;
  city: string | null;
  latitude: number | null;
  longitude: number | null;
  user_agent: string | null;
  timezone: string | null;
  language: string | null;
  platform: string | null;
  request_count: number;
};

export type LiveAnalyticsResponse = {
  generated_at: string;
  window_minutes: number;
  total: number;
  authenticated: number;
  anonymous: number;
  role_counts: Record<string, number>;
  raw_ip_enabled: boolean;
  geo_enabled: boolean;
  sessions: AnalyticsSession[];
};

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === 'string') return body.detail;
    return JSON.stringify(body?.detail ?? body);
  } catch {
    return response.statusText || 'İstek başarısız oldu.';
  }
}

export async function getLiveAnalytics(
  minutes = 5,
  limit = 100,
): Promise<LiveAnalyticsResponse> {
  const token = getAccessToken();
  if (!token) throw new Error('Yönetici oturumu bulunamadı.');

  const url = new URL(`${API_BASE_URL.replace(/\/$/, '')}/analytics/live`);
  url.searchParams.set('minutes', String(minutes));
  url.searchParams.set('limit', String(limit));

  const response = await fetch(url.toString(), {
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  return (await response.json()) as LiveAnalyticsResponse;
}
