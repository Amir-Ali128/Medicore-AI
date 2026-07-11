import { getAccessToken } from './authClient';
import type { ClinicalHypothesis } from './clinicalHypothesesClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export type ClaudeReviewGenerationResult = {
  analysis_run_id: string;
  lab_report_id: string | null;
  patient_id: string | null;
  created_hypotheses: ClinicalHypothesis[];
  drafts_count: number;
  created_count: number;
  warnings: string[];
  hypotheses?: ClinicalHypothesis[];
  generated_count?: number;
};

function authHeaders(): HeadersInit {
  const token = getAccessToken();

  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function readErrorMessage(response: Response): Promise<string> {
  const contentType = response.headers.get('content-type') ?? '';

  if (contentType.includes('application/json')) {
    try {
      const body = await response.json();

      if (typeof body?.detail === 'string') {
        return body.detail;
      }

      return JSON.stringify(body);
    } catch {
      return response.statusText;
    }
  }

  return response.text();
}

export async function generateClaudeAbnormalReview(
  analysisRunId: string,
  maxHypotheses: number,
): Promise<ClaudeReviewGenerationResult> {
  const response = await fetch(
    `${API_BASE_URL}/analysis-runs/${analysisRunId}/clinical-hypotheses/generate`,
    {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        max_hypotheses: Math.max(1, Math.min(maxHypotheses, 10)),
        include_normal_results: false,
        include_needs_review_only: false,
        min_confidence: null,
        language: 'tr',
        metadata_json: {
          source: 'lab_analysis_abnormal_review',
          normal_results_excluded: true,
        },
      }),
    },
  );

  if (!response.ok) {
    const detail = await readErrorMessage(response);
    throw new Error(`Claude review failed: ${response.status} ${detail}`);
  }

  return response.json();
}
