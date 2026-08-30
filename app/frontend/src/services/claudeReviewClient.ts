import { getAccessToken } from './authClient';
import type { ClinicalHypothesis } from './clinicalHypothesesClient';
import type { ClinicalIntakeInput } from './labAnalysisClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

const ACTIVE_CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';

export type ClaudeClinicalContext = ClinicalIntakeInput;

export type ClaudeSuggestedTest = {
  name: string;
  rationale: string | null;
  priority: 'routine' | 'soon' | 'urgent' | null;
};

export type ClaudePathologicalFinding = {
  source: 'laboratory' | 'vital';
  name: string;
  status: string;
  status_label: string;
  value: string | null;
  unit: string | null;
  display: string;
};

export type ClaudeEvaluationMetadata = Record<string, unknown> & {
  risk?: number;
  flags?: string[];
  symptoms?: string[];
  pathological_findings?: ClaudePathologicalFinding[];
  pathological_count?: number;
  pathological_findings_source?: string;
  ai_called?: boolean;
  compact_mode?: boolean;
  max_output_tokens?: number;
  possible_conditions?: string[];
  recommended_laboratory_tests?: ClaudeSuggestedTest[];
  recommended_imaging_tests?: ClaudeSuggestedTest[];
  limitations?: string[];
  requires_physician_review?: boolean;
};

export type ClaudeEvaluationHypothesis = ClinicalHypothesis & {
  metadata_json: ClaudeEvaluationMetadata;
};

export type ClaudeReviewGenerationResult = {
  analysis_run_id: string;
  lab_report_id: string | null;
  patient_id: string | null;
  created_hypotheses: ClaudeEvaluationHypothesis[];
  drafts_count: number;
  created_count: number;
  warnings: string[];
  hypotheses?: ClaudeEvaluationHypothesis[];
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

function readStoredClinicalContext(): ClaudeClinicalContext | undefined {
  try {
    const raw = localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY);
    if (!raw) return undefined;
    return JSON.parse(raw) as ClaudeClinicalContext;
  } catch {
    return undefined;
  }
}

function cleanText(value: string | null | undefined) {
  const cleaned = value?.replace(/\s+/g, ' ').trim();
  return cleaned ? cleaned.slice(0, 240) : null;
}

function buildCompactSymptoms(
  context: ClaudeClinicalContext | undefined,
): string[] {
  const complaint = context?.presenting_complaint;
  if (!complaint) return [];

  const chief = cleanText(complaint.chief_complaint);
  const duration = cleanText(complaint.complaint_duration);
  const values = [
    chief && duration ? `${chief} (${duration})`.slice(0, 240) : chief,
    cleanText(complaint.associated_symptoms),
    cleanText(complaint.reason_for_visit),
  ].filter((value): value is string => Boolean(value));

  return [...new Set(values)].slice(0, 4);
}

function buildCompactVitals(
  context: ClaudeClinicalContext | undefined,
): Record<string, number | string | null> {
  const exam = context?.physical_exam;
  if (!exam) return {};

  return {
    blood_pressure_systolic: exam.blood_pressure_systolic ?? null,
    blood_pressure_diastolic: exam.blood_pressure_diastolic ?? null,
    pulse_bpm: exam.pulse_bpm ?? null,
    temperature_c: exam.temperature_c ?? null,
    respiratory_rate: exam.respiratory_rate ?? null,
    oxygen_saturation_percent: exam.oxygen_saturation_percent ?? null,
  };
}

export async function evaluateClaudeAbnormalResults(
  analysisRunId: string,
  maxHypotheses: number,
  clinicalContext?: ClaudeClinicalContext,
): Promise<ClaudeReviewGenerationResult> {
  // Kept in the public function signature for older callers. Compact mode always
  // returns at most one short risk summary.
  void maxHypotheses;

  const context = readStoredClinicalContext() ?? clinicalContext;
  const symptoms = buildCompactSymptoms(context);
  const vitals = buildCompactVitals(context);

  const response = await fetch(
    `${API_BASE_URL}/analysis-runs/${analysisRunId}/clinical-hypotheses/generate`,
    {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        max_hypotheses: 1,
        include_normal_results: false,
        include_needs_review_only: false,
        min_confidence: null,
        language: 'tr',
        metadata_json: {
          source: 'compact_rule_gated_evaluation',
          normal_results_excluded: true,
          symptoms,
          vitals,
        },
      }),
    },
  );

  if (!response.ok) {
    const detail = await readErrorMessage(response);
    throw new Error(`Claude değerlendirmesi başarısız: ${response.status} ${detail}`);
  }

  const result = (await response.json()) as ClaudeReviewGenerationResult;
  window.dispatchEvent(new Event('medicore:case-summary-updated'));
  return result;
}

/** Backward-compatible alias for older callers. */
export const generateClaudeAbnormalReview = evaluateClaudeAbnormalResults;
