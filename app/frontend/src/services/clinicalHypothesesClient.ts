import { getAccessToken } from './authClient';
import {
  getAnalysisRunResults,
  type LabAnalysisResult,
} from './labAnalysisClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

const DEMO_PATIENT_ID = '3fa85f64-5717-4562-b3fc-2c963f66afa6';
const DEMO_DOCTOR_ID = '3fa85f64-5717-4562-b3fc-2c963f66afa6';

export type ClinicalEvidenceItem = {
  parameter_code: string | null;
  parameter_name: string | null;
  value: string | null;
  unit: string | null;
  result_status: string | null;
  note: string | null;
};

export type ClinicalHypothesis = {
  id: string;
  patient_id: string;
  lab_report_id: string | null;
  analysis_run_id: string | null;
  title: string;
  summary: string;
  hypothesis_type: string | null;
  confidence: number | null;
  severity: string | null;
  status: string;
  source: string;
  evidence_json: ClinicalEvidenceItem[];
  needs_doctor_review: boolean;
  reviewed_at: string | null;
  reviewed_by_user_id: string | null;
  created_at: string;
  updated_at: string;
};

export type CreateClinicalHypothesisPayload = {
  patient_id: string;
  lab_report_id: string | null;
  analysis_run_id: string | null;
  title: string;
  summary: string;
  hypothesis_type: string | null;
  confidence: number | null;
  severity: string | null;
  source: string;
  evidence_json: ClinicalEvidenceItem[];
  metadata_json: Record<string, unknown>;
};

export type DoctorReviewAction =
  | 'approve'
  | 'reject'
  | 'edit'
  | 'request_extra_test'
  | 'refer_specialist';

export type DoctorReview = {
  id: string;
  clinical_hypothesis_id: string;
  doctor_id: string;
  action: DoctorReviewAction;
  doctor_note: string | null;
  edited_title: string | null;
  edited_summary: string | null;
  requested_tests_json: string[] | null;
  specialist_referral: string | null;
  reviewed_at: string;
  created_at: string;
  updated_at: string;
};

export type DoctorReviewActionResponse = {
  clinical_hypothesis: ClinicalHypothesis;
  doctor_review: DoctorReview;
};

function getAuthHeaders() {
  const token = getAccessToken();

  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function getPrimaryResult(results: LabAnalysisResult[]) {
  const abnormalResult = results.find(
    (result) =>
      result.result_status === 'low' || result.result_status === 'high',
  );

  return abnormalResult ?? results[0];
}

function buildEvidenceItem(result: LabAnalysisResult): ClinicalEvidenceItem {
  return {
    parameter_code: result.parameter_code,
    parameter_name: result.canonical_name ?? result.raw_parameter_name,
    value: result.normalized_value,
    unit: result.unit,
    result_status: result.result_status,
    note: result.reason,
  };
}

function buildDemoTitle(result: LabAnalysisResult) {
  const parameterName = result.canonical_name ?? result.raw_parameter_name;

  if (result.result_status === 'low') {
    return `${parameterName} below reference range — physician review prompt`;
  }

  if (result.result_status === 'high') {
    return `${parameterName} above reference range — physician review prompt`;
  }

  return `${parameterName} review prompt`;
}

function buildDemoSummary(result: LabAnalysisResult) {
  const parameterName = result.canonical_name ?? result.raw_parameter_name;

  return `${parameterName} result is ${result.normalized_value} ${result.unit}. ${result.reason} This is a structured review prompt only and is not a diagnosis.`;
}

function buildSeverity(result: LabAnalysisResult) {
  if (result.result_status === 'low' || result.result_status === 'high') {
    return 'medium';
  }

  return 'low';
}

export async function getClinicalHypothesesForAnalysisRun(
  analysisRunId: string,
): Promise<ClinicalHypothesis[]> {
  const response = await fetch(
    `${API_BASE_URL}/analysis-runs/${analysisRunId}/clinical-hypotheses`,
    {
      headers: getAuthHeaders(),
    },
  );

  if (!response.ok) {
    const errorText = await response.text();

    throw new Error(
      `Clinical hypotheses fetch failed: ${response.status} ${errorText}`,
    );
  }

  return response.json();
}

export async function getPendingClinicalHypotheses(): Promise<
  ClinicalHypothesis[]
> {
  const response = await fetch(
    `${API_BASE_URL}/clinical-hypotheses/status/pending`,
    {
      headers: getAuthHeaders(),
    },
  );

  if (!response.ok) {
    const errorText = await response.text();

    throw new Error(
      `Pending clinical hypotheses fetch failed: ${response.status} ${errorText}`,
    );
  }

  return response.json();
}

export async function createClinicalHypothesis(
  payload: CreateClinicalHypothesisPayload,
): Promise<ClinicalHypothesis> {
  const response = await fetch(`${API_BASE_URL}/clinical-hypotheses`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();

    throw new Error(
      `Clinical hypothesis creation failed: ${response.status} ${errorText}`,
    );
  }

  return response.json();
}

export async function createDemoClinicalHypothesis(
  analysisRunId: string,
  labReportId: string | null,
): Promise<ClinicalHypothesis> {
  const results = await getAnalysisRunResults(analysisRunId);
  const primaryResult = getPrimaryResult(results);

  if (!primaryResult) {
    throw new Error('No lab result found for this analysis run.');
  }

  return createClinicalHypothesis({
    patient_id: DEMO_PATIENT_ID,
    lab_report_id: labReportId,
    analysis_run_id: analysisRunId,
    title: buildDemoTitle(primaryResult),
    summary: buildDemoSummary(primaryResult),
    hypothesis_type: 'lab_signal_review',
    confidence: primaryResult.classification_confidence ?? 0.75,
    severity: buildSeverity(primaryResult),
    source: 'frontend_demo',
    evidence_json: [buildEvidenceItem(primaryResult)],
    metadata_json: {
      generated_from: 'frontend_demo_button',
      safety_note:
        'This is a physician-review prompt only and is not a diagnosis.',
    },
  });
}

export async function applyDoctorReview(
  clinicalHypothesisId: string,
  action: DoctorReviewAction,
  doctorNote: string,
): Promise<DoctorReviewActionResponse> {
  const response = await fetch(
    `${API_BASE_URL}/clinical-hypotheses/${clinicalHypothesisId}/reviews`,
    {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        doctor_id: DEMO_DOCTOR_ID,
        action,
        doctor_note: doctorNote,
        edited_title: null,
        edited_summary: null,
        requested_tests_json: null,
        specialist_referral: null,
        metadata_json: {
          source: 'frontend_doctor_review',
        },
      }),
    },
  );

  if (!response.ok) {
    const errorText = await response.text();

    throw new Error(
      `Doctor review action failed: ${response.status} ${errorText}`,
    );
  }

  return response.json();
}