import { getAccessToken } from './authClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export type LabFileSource =
  | 'enabiz-pdf'
  | 'file'
  | 'photo'
  | 'screenshot'
  | 'email-attachment';

export type LabIntegrationType = 'hl7_oru' | 'fhir' | 'rest';

export type LongitudinalTrend = {
  contract_version?: string;
  backend?: string;
  test?: string | null;
  parameter_code?: string | null;
  previous_result_id?: string | null;
  previous_value?: number | string | null;
  current_value?: number | string | null;
  previous_measured_at?: string | null;
  current_measured_at?: string | null;
  trend_status?: string;
  absolute_difference?: number | string | null;
  percentage_difference?: number | null;
  time_difference_days?: number | null;
  confidence?: number;
  reason?: string;
  needs_review?: boolean;
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
};

export type UniversalLabIngestionResponse = {
  contract_version?: string;
  source_type?: string;
  source?: Record<string, unknown>;
  trusted_count?: number;
  review_count?: number;
  processed_row_count?: number;
  ai_attempted?: boolean;
  ai_used?: boolean;
  doctor_review_required?: boolean;
  native_trends_used_by_ai?: number;
  longitudinal_trends?: LongitudinalTrend[];
  patient_history?: PatientHistorySnapshot;
  history_contract_version?: string;
  clinical_assessment?: {
    headline?: string;
    overview?: string;
    narrative_tr?: string;
    synthesis_source?: string;
    fallback_reason?: string;
    [key: string]: unknown;
  } | null;
  trusted_rows?: Array<Record<string, unknown>>;
  review_rows?: Array<Record<string, unknown>>;
  derived_metrics?: Array<Record<string, unknown>>;
  [key: string]: unknown;
};

export type ManualLabRowInput = {
  raw_parameter_name: string;
  raw_value: string;
  normalized_value: number;
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

export type IngestionOptions = {
  patientId?: string | null;
  clinicalAi?: boolean;
  sourceRecordId?: string | null;
};

function authHeaders(extra?: HeadersInit): HeadersInit {
  const token = getAccessToken();
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(extra ?? {}),
  };
}

function buildUrl(path: string, options: IngestionOptions = {}) {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (options.patientId) url.searchParams.set('patient_id', options.patientId);
  if (options.clinicalAi !== false) url.searchParams.set('clinical_ai', 'true');
  if (options.sourceRecordId) url.searchParams.set('source_record_id', options.sourceRecordId);
  return url.toString();
}

async function readErrorMessage(response: Response): Promise<string> {
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') return body.detail;
      return JSON.stringify(body);
    } catch {
      return response.statusText || 'İstek başarısız oldu.';
    }
  }
  const text = await response.text();
  return text || response.statusText || 'İstek başarısız oldu.';
}

async function parseResponse(response: Response): Promise<UniversalLabIngestionResponse> {
  if (!response.ok) throw new Error(await readErrorMessage(response));
  return response.json() as Promise<UniversalLabIngestionResponse>;
}

export async function ingestLabFile(
  source: LabFileSource,
  file: File,
  options: IngestionOptions = {},
): Promise<UniversalLabIngestionResponse> {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(buildUrl(`/lab-ingestion/${source}`, options), {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  });
  return parseResponse(response);
}

export async function ingestManualLabs(
  payload: ManualLabPayload,
  options: IngestionOptions = {},
): Promise<UniversalLabIngestionResponse> {
  const response = await fetch(buildUrl('/lab-ingestion/manual', options), {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function ingestLabIntegration(
  integrationType: LabIntegrationType,
  payload: unknown,
  options: IngestionOptions = {},
): Promise<UniversalLabIngestionResponse> {
  const response = await fetch(buildUrl('/lab-ingestion/integration', options), {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      integration_type: integrationType,
      payload,
      source_record_id: options.sourceRecordId || null,
    }),
  });
  return parseResponse(response);
}

export async function evaluateSavedLabReport(
  labReportId: string,
): Promise<UniversalLabIngestionResponse> {
  const response = await fetch(
    `${API_BASE_URL}/lab-ingestion/reports/${encodeURIComponent(labReportId)}/evaluate`,
    {
      method: 'POST',
      headers: authHeaders(),
    },
  );
  return parseResponse(response);
}
