import { API_BASE_URL, apiClient } from './apiClient';
import { getAccessToken } from './authClient';

export type SexValue = 'female' | 'male' | 'other' | 'unknown';
export type VitalSigns = {
  systolic_bp: number | null;
  diastolic_bp: number | null;
  heart_rate: number | null;
  respiratory_rate: number | null;
  temperature: number | null;
  spo2: number | null;
  height_cm: number | null;
  weight_kg: number | null;
  glucose_mg_dl: number | null;
};

export type ClinicalContext = {
  age: number | null;
  sex: SexValue;
  complaints: string[];
  history: string[];
  medications: string[];
  notes: string | null;
  vital_signs?: VitalSigns | null;
  event_date?: string | null;
  vitals_event_date?: string | null;
};

export type LabReference = {
  text: string;
  minimum?: number | null;
  maximum?: number | null;
  unit?: string | null;
  age_min?: number | null;
  age_max?: number | null;
  sex?: SexValue | null;
};

export type CanonicalLabStatus = 'LOW' | 'NORMAL' | 'HIGH' | 'UNKNOWN';

export type DocumentDates = {
  event_date?: string | null;
  specimen_date?: string | null;
  result_date?: string | null;
  document_date?: string | null;
  uploaded_at?: string | null;
};

export type CanonicalLabClassification = {
  status?: CanonicalLabStatus;
  reference_low?: number | null;
  reference_high?: number | null;
  raw_reference?: string | null;
  classification_reason?: string | null;
};

export type LabInput = DocumentDates & CanonicalLabClassification & {
  test_name: string;
  value: string | number | null;
  unit: string | null;
  measured_at?: string | null;
  source_reference: string | null;
  source_references: LabReference[];
  source_metadata?: Record<string, unknown>;
};

export type LabOutput = DocumentDates & CanonicalLabClassification & {
  test_name: string;
  value: string | number | null;
  unit: string | null;
  measured_at?: string | null;
  reference_text: string | null;
  reference_source: 'report' | 'report_age_sex_match' | 'missing';
  reference_details?: LabReference | null;
  source_reference?: string | null;
  source_references?: LabReference[];
  source_metadata?: Record<string, unknown>;
};

export type MedicalReportInput = Omit<DocumentDates, 'specimen_date' | 'result_date'> & {
  report_type: string;
  report_date?: string | null;
  exam_date?: string | null;
  consultation_date?: string | null;
  body_region: string | null;
  findings: string | null;
  impression: string | null;
  raw_text: string | null;
  metadata?: Record<string, unknown>;
};

export type SimpleCaseRequest = {
  clinical: ClinicalContext;
  labs: LabInput[];
  reports: MedicalReportInput[];
};

export type SimpleCaseResponse = {
  contract_version: 'medicore-simple-case-v1';
  clinical: ClinicalContext;
  labs: LabOutput[];
  reports: MedicalReportInput[];
  warnings: string[];
};

export type CaseAIInterpretation = {
  report_text: string;
  model: string;
};

export type SavedSimpleCase = {
  patient_id: string;
  protocol_no: string;
  case_name?: string;
  sex: SexValue;
  age: number | null;
  clinical?: ClinicalContext;
  simple_case: {
    contract_version: 'medicore-simple-case-v1';
    clinical: ClinicalContext;
    labs: LabOutput[];
    reports: MedicalReportInput[];
    warnings: string[];
  } | null;
  ai_report: CaseAIInterpretation | null;
};

export type PatientRecord = {
  id: string;
  protocol_no: string;
  sex: SexValue;
  metadata_json: Record<string, unknown>;
};

type UploadInit = {
  method?: 'POST' | 'PUT';
  body: FormData;
  signal?: AbortSignal;
};

async function uploadRequest<T>(path: string, init: UploadInit): Promise<T> {
  const token = getAccessToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: init.method ?? 'POST',
    body: init.body,
    signal: init.signal,
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? String((body as { detail?: unknown }).detail ?? '')
        : '';
    throw new Error(detail || `İstek başarısız: ${response.status}`);
  }
  return body as T;
}

export function normalizeSimpleCase(payload: SimpleCaseRequest) {
  return apiClient.post<SimpleCaseResponse>('/simple-case/normalize', payload);
}

export function createPatient(payload: {
  protocol_no: string;
  age: number | null;
  sex: SexValue;
  clinical_context: Record<string, unknown>;
}, signal?: AbortSignal) {
  return apiClient.post<PatientRecord>('/patients', {
    ...payload,
    height_cm: null,
    weight_kg: null,
  }, { signal });
}

export function saveSimpleCase(patientId: string, payload: SimpleCaseRequest, signal?: AbortSignal) {
  return apiClient.put<SimpleCaseResponse>(
    `/simple-case/patients/${patientId}/save`,
    payload,
    { signal },
  );
}

export function uploadLabPdf(file: File, signal?: AbortSignal) {
  const body = new FormData();
  body.append('file', file);
  return uploadRequest<LabInput[]>('/simple-case/labs/pdf', { body, signal });
}

export function uploadLabImage(file: File, rotation = 0, signal?: AbortSignal) {
  const body = new FormData();
  body.append('file', file);
  body.append('rotation', String(rotation));
  return uploadRequest<LabInput[]>('/simple-case/labs/image', { body, signal });
}

export function uploadReportPdf(
  file: File,
  reportType: string,
  bodyRegion: string,
  signal?: AbortSignal,
) {
  const body = new FormData();
  body.append('file', file);
  body.append('report_type', reportType || 'Tıbbi Rapor');
  if (bodyRegion.trim()) body.append('body_region', bodyRegion.trim());
  return uploadRequest<MedicalReportInput>('/simple-case/reports/pdf', { body, signal });
}

export function uploadReportImage(
  file: File,
  reportType: string,
  bodyRegion: string,
  signal?: AbortSignal,
) {
  const body = new FormData();
  body.append('file', file);
  body.append('report_type', reportType || 'Tıbbi Rapor');
  if (bodyRegion.trim()) body.append('body_region', bodyRegion.trim());
  return uploadRequest<MedicalReportInput>('/simple-case/reports/image', { body, signal });
}


export function interpretSimpleCase(
  payload: SimpleCaseRequest,
  patientId?: string | null,
  signal?: AbortSignal,
) {
  const path = patientId
    ? `/simple-case/patients/${patientId}/ai-interpretation`
    : '/simple-case/ai-interpretation';
  return apiClient.post<CaseAIInterpretation>(path, payload, { signal });
}


export function getSavedSimpleCase(patientId: string, signal?: AbortSignal) {
  return apiClient.get<SavedSimpleCase>(`/simple-case/patients/${patientId}`, { signal });
}
