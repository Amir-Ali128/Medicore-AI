import { getAccessToken } from './authClient';
import { API_BASE_URL } from './apiClient';

export type LabFileIngestionSource =
  | 'enabiz-pdf'
  | 'file'
  | 'photo'
  | 'screenshot'
  | 'email-attachment';

export type LabIntegrationType = 'hl7_oru' | 'fhir' | 'rest';

export type LabTrustRow = {
  raw_parameter_name?: string | null;
  canonical_name?: string | null;
  display_name?: string | null;
  raw_value?: string | number | null;
  normalized_value?: string | number | null;
  raw_unit?: string | null;
  unit?: string | null;
  reference_min?: string | number | null;
  reference_max?: string | number | null;
  reference_text?: string | null;
  result_status?: string | null;
  validation_status?: string | null;
  trust_status?: string | null;
  trusted_for_ai?: boolean;
  needs_review?: boolean;
  trust_reason?: string | null;
  reason?: string | null;
  measured_at?: string | null;
  [key: string]: unknown;
};

export type LongitudinalLabTrend = {
  backend?: string | null;
  test?: string | null;
  parameter_code?: string | null;
  previous_value?: string | number | null;
  current_value?: string | number | null;
  previous_measured_at?: string | null;
  current_measured_at?: string | null;
  trend_status?: string | null;
  absolute_difference?: string | number | null;
  percentage_difference?: number | null;
  time_difference_days?: number | null;
  confidence?: number | null;
  needs_review?: boolean;
  reason?: string | null;
  [key: string]: unknown;
};

export type PatientHistorySnapshot = {
  contract_version?: string;
  patient_id?: string;
  lab_report_id?: string;
  persisted_result_count?: number;
  trusted_count?: number;
  review_count?: number;
  trend_count?: number;
  doctor_review_required?: boolean;
  [key: string]: unknown;
};

export type ClinicalAssessment = {
  headline?: string;
  overview?: string;
  narrative_tr?: string;
  synthesis_source?: string;
  fallback_reason?: string;
  priority_findings?: Array<{
    title?: string;
    severity?: string;
    summary?: string;
    evidence?: string[];
  }>;
  priority_actions?: string[];
  reassuring_findings?: string[];
  [key: string]: unknown;
};

export type UniversalLabIngestionResponse = {
  contract_version?: string;
  source_type?: string;
  trusted_count?: number;
  review_count?: number;
  processed_row_count?: number;
  trusted_rows?: LabTrustRow[];
  review_rows?: LabTrustRow[];
  all_rows?: LabTrustRow[];
  longitudinal_trends?: LongitudinalLabTrend[];
  derived_metrics?: Array<Record<string, unknown>>;
  clinical_assessment?: ClinicalAssessment;
  ai_attempted?: boolean;
  ai_used?: boolean;
  doctor_review_required?: boolean;
  patient_history?: PatientHistorySnapshot;
  history_contract_version?: string;
  native_trends_used_by_ai?: number;
  [key: string]: unknown;
};

export type LabIngestionOptions = {
  patientId?: string | null;
  clinicalAi?: boolean;
};

export type ManualLabRowInput = {
  raw_parameter_name: string;
  raw_value?: string | null;
  normalized_value?: number | null;
  unit?: string | null;
  reference_min?: number | null;
  reference_max?: number | null;
  reference_text?: string | null;
  measured_at?: string | null;
};

export type ManualLabPayload = {
  labs: ManualLabRowInput[];
  patient_age?: number | null;
  patient_sex?: string | null;
  report_date?: string | null;
  source_record_id?: string | null;
};

export type IntegrationLabPayload = {
  integration_type: LabIntegrationType;
  payload: unknown;
  source_record_id?: string | null;
};

function authHeaders(extra?: HeadersInit): HeadersInit {
  const token = getAccessToken();
  return {
    Accept: 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
}

function buildUrl(path: string, options: LabIngestionOptions = {}) {
  const query = new URLSearchParams();
  if (options.clinicalAi ?? true) query.set('clinical_ai', 'true');
  if (options.patientId) query.set('patient_id', options.patientId);
  const suffix = query.toString();
  return `${API_BASE_URL}/lab-ingestion/${path}${suffix ? `?${suffix}` : ''}`;
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === 'string') return body.detail;
    return JSON.stringify(body);
  } catch {
    return response.statusText || 'Bilinmeyen API hatası';
  }
}

async function parseResponse(response: Response): Promise<UniversalLabIngestionResponse> {
  if (!response.ok) {
    throw new Error(`Laboratuvar girişi başarısız: ${response.status} ${await readError(response)}`);
  }
  return response.json() as Promise<UniversalLabIngestionResponse>;
}

export async function ingestLabFile(
  source: LabFileIngestionSource,
  file: File,
  options: LabIngestionOptions = {},
): Promise<UniversalLabIngestionResponse> {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(buildUrl(source, options), {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  });
  return parseResponse(response);
}

export async function ingestManualLabs(
  payload: ManualLabPayload,
  options: LabIngestionOptions = {},
): Promise<UniversalLabIngestionResponse> {
  const response = await fetch(buildUrl('manual', options), {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function ingestLabIntegration(
  payload: IntegrationLabPayload,
  options: LabIngestionOptions = {},
): Promise<UniversalLabIngestionResponse> {
  const response = await fetch(buildUrl('integration', options), {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function getLabIngestionCapabilities(): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE_URL}/lab-ingestion/capabilities`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(`Laboratuvar özellikleri alınamadı: ${response.status} ${await readError(response)}`);
  }
  return response.json() as Promise<Record<string, unknown>>;
}
