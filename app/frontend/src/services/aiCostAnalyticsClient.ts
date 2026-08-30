import { getAccessToken } from './authClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  import.meta.env.VITE_MEDICORE_API_BASE_URL ??
  'http://127.0.0.1:8000';

export type AiCostEvent = {
  id: string;
  analysis_run_id: string | null;
  created_at: string;
  model: string | null;
  ai_called: boolean;
  generated_by: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  estimated_cost_usd: number | null;
};

export type AiCostAnalyticsResponse = {
  generated_at: string;
  window_minutes: number;
  compact_evaluations: number;
  tracked_calls: number;
  untracked_ai_calls: number;
  fallback_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  pricing: {
    model: string;
    input_per_million_usd: number;
    output_per_million_usd: number;
    source: string;
  };
  events: AiCostEvent[];
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

export async function getAiCostAnalytics(
  minutes = 1440,
  limit = 100,
): Promise<AiCostAnalyticsResponse> {
  const token = getAccessToken();
  if (!token) throw new Error('Yönetici oturumu bulunamadı.');

  const url = new URL(`${API_BASE_URL.replace(/\/$/, '')}/analytics/ai-costs`);
  url.searchParams.set('minutes', String(minutes));
  url.searchParams.set('limit', String(limit));

  const response = await fetch(url.toString(), {
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as AiCostAnalyticsResponse;
}
