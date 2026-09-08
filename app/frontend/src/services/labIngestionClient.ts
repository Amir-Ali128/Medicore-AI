import { getAccessToken } from './authClient';
import { API_BASE_URL } from './apiClient';

export type LabIngestionSource =
  | 'enabiz-pdf'
  | 'file'
  | 'photo'
  | 'screenshot'
  | 'manual'
  | 'email-attachment'
  | 'integration';

export type LabIngestionOptions = {
  patientId?: string | null;
  clinicalAi?: boolean;
  sourceRecordId?: string | null;
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

export type IntegrationType = 'hl7_oru' | 'fhir' | 'rest';

export type IntegrationLabPayload = {
  integration_type: IntegrationType;
  payload: unknown;
  source_record_id?: string | null;
};

export type LabTrustRow = {
  raw_parameter_name?: string | null;
  canonical_name?: string | null;
  display_name?: string | null;
  raw_value?: string | null;
  normalized_value?: number | null;
  unit?: string | null;
  result_status?: string | null;
  validation_status?: string | null;
  trust_status?: string | null;
  trusted_for_ai?: boolean;
  needs_review?: boolean;
  trust_reason?: string | null;
  reason?: string | null;
};

export type LongitudinalTrend = {
  contract_version?: string;
  backend?: 'native_cpp' | 'python_fallback' | string;
  test?: string | null;
  parameter_code?: string | null;
  previous_result_id?: string | null;
  previous_value?: number | null;
  current_value?: number | null;
  previous_measured_at?: string | null;
  current_measured_at?: string | null;
  trend_status?: string | null;
  absolute_difference?: number | null;
  percentage_difference?: number | null;
  time_difference_days?: number | null;
  confidence?: number | null;
  reason?: string | null;
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

export type LabIngestionResponse = {
  contract_version?: string;
  source_type?: string;
  trusted_count?: number;
  review_count?: number;
  processed_row_count?: number;
  trusted_rows?: LabTrustRow[];
  review_rows?: LabTrustRow[];
  all_rows?: LabTrustRow[];
  longitudinal_trends?: LongitudinalTrend[];
  clinical_assessment?: Record<string, unknown>;
  ai_attempted?: boolean;
  ai_used?: boolean;
  doctor_review_required?: boolean;
  patient_history?: PatientHistorySnapshot;
  history_contract_version?: string;
  [key: string]: unknown;
};

export type LabIngestionCapabilities = {
  contract_version?: string;
  source_count?: number;
  sources?: Array<{
    source_type?: string;
    input?: string;
    formats?: string[];
  }>;
  downstream_contract?: string;
  native_trust_required?: boolean;
  clinical_ai_optional?: boolean;
  patient_history_optional?: boolean;
  [key: string]: unknown;
};

export class LabIngestionClientError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = 'LabIngestionClientError';
    this.status = status;
    this.body = body;
  }
}

function buildQuery(options: LabIngestionOptions = {}) {
  const params = new URLSearchParams();
  if (options.patientId) params.set('patient_id', options.patientId);
  if (options.clinicalAi) params.set('clinical_ai', 'true');
  if (options.sourceRecordId) params.set('source_record_id', options.sourceRecordId);
  const query = params.toString();
  return query ? `?${query}` : '';
}

async function parseResponse(response: Response) {
  const contentType = response.headers.get('content-type') ?? '';
  if (response.status === 204) return undefined;
  if (contentType.includes('application/json')) return response.json();
  return response.text();
}

function errorMessage(body: unknown, fallback: string) {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
  }
  if (typeof body === 'string' && body.trim()) return body;
  return fallback;
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const token = getAccessToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  const body = await parseResponse(response);
  if (!response.ok) {
    throw new LabIngestionClientError(
      response.status,
      errorMessage(body, `Laboratuvar isteği başarısız oldu (${response.status}).`),
      body,
    );
  }
  return body as T;
}

export function getLabIngestionCapabilities() {
  return request<LabIngestionCapabilities>('/lab-ingestion/capabilities', {
    method: 'GET',
  });
}

export function uploadLabIngestionFile(
  source: Exclude<LabIngestionSource, 'manual' | 'integration'>,
  file: File,
  options: LabIngestionOptions = {},
) {
  const form = new FormData();
  form.append('file', file);
  return request<LabIngestionResponse>(
    `/lab-ingestion/${source}${buildQuery(options)}`,
    {
      method: 'POST',
      body: form,
    },
  );
}

export function submitManualLabIngestion(
  payload: ManualLabPayload,
  options: LabIngestionOptions = {},
) {
  return request<LabIngestionResponse>(
    `/lab-ingestion/manual${buildQuery(options)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  );
}

export function submitIntegrationLabIngestion(
  payload: IntegrationLabPayload,
  options: LabIngestionOptions = {},
) {
  return request<LabIngestionResponse>(
    `/lab-ingestion/integration${buildQuery(options)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  );
}
