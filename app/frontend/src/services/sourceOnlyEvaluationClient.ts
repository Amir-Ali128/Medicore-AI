import { getAccessToken } from './authClient';
import type { ClinicalHypothesis } from './clinicalHypothesesClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

function authHeaders(): HeadersInit {
  const token = getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function isSourceOnlyCompact(hypothesis: ClinicalHypothesis) {
  return (
    hypothesis.analysis_run_id === null &&
    hypothesis.hypothesis_type === 'compact_risk_summary' &&
    hypothesis.metadata_json?.source_evaluation_scope === 'source_only'
  );
}

export async function getSourceOnlyEvaluationsForPatient(
  patientId: string,
): Promise<ClinicalHypothesis[]> {
  const response = await fetch(
    `${API_BASE_URL}/patients/${patientId}/clinical-hypotheses`,
    { headers: authHeaders() },
  );

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(
      `Tek kaynaklı değerlendirmeler yüklenemedi: ${response.status} ${detail}`,
    );
  }

  const hypotheses = (await response.json()) as ClinicalHypothesis[];
  return hypotheses.filter(isSourceOnlyCompact);
}

export async function deleteSourceOnlyEvaluationsForPatient(
  patientId: string,
): Promise<number> {
  const response = await fetch(
    `${API_BASE_URL}/patients/${patientId}/clinical-hypotheses/compact/source-only`,
    {
      method: 'DELETE',
      headers: authHeaders(),
    },
  );

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(
      `Tek kaynaklı değerlendirme silinemedi: ${response.status} ${detail}`,
    );
  }

  const body = (await response.json()) as { deleted_count?: number };
  return body.deleted_count ?? 0;
}
