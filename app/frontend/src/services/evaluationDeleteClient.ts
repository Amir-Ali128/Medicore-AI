import { getAccessToken } from './authClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export async function deleteCompactEvaluation(analysisRunId: string) {
  const token = getAccessToken();
  const response = await fetch(
    `${API_BASE_URL}/analysis-runs/${analysisRunId}/clinical-hypotheses/compact`,
    {
      method: 'DELETE',
      headers: {
        Accept: 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    },
  );

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
      // Keep status text.
    }
    throw new Error(`AI değerlendirmesi silinemedi: ${response.status} ${detail}`);
  }

  return (await response.json()) as { deleted_count: number };
}
