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

export type LabInput = {
  test_name: string;
  value: string | number | null;
  unit: string | null;
  measured_at?: string | null;
  source_reference: string | null;
  source_references: LabReference[];
  source_metadata?: Record<string, unknown>;
};

export type MedicalReportInput = {
  report_type: string;
  report_date?: string | null;
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
  labs: Array<{
    test_name: string;
    value: string | number | null;
    unit: string | null;
    reference_text: string | null;
    reference_source: 'report' | 'report_age_sex_match' | 'missing';
  }>;
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
  sex: SexValue;
  age: number | null;
  clinical?: ClinicalContext;
  simple_case: {
    contract_version: 'medicore-simple-case-v1';
    clinical: ClinicalContext;
    labs: Array<{
      test_name: string;
      value: string | number | null;
      unit: string | null;
      measured_at?: string | null;
      reference_text: string | null;
      reference_source: 'report' | 'report_age_sex_match' | 'missing';
      reference_details?: LabReference | null;
      source_metadata?: Record<string, unknown>;
    }>;
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
};

async function uploadRequest<T>(path: string, init: UploadInit): Promise<T> {
  const token = getAccessToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: init.method ?? 'POST',
    body: init.body,
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
}) {
  return apiClient.post<PatientRecord>('/patients', {
    ...payload,
    height_cm: null,
    weight_kg: null,
  });
}

export function saveSimpleCase(patientId: string, payload: SimpleCaseRequest) {
  return apiClient.put<SimpleCaseResponse>(
    `/simple-case/patients/${patientId}/save`,
    payload,
  );
}

export function uploadLabPdf(file: File) {
  const body = new FormData();
  body.append('file', file);
  return uploadRequest<LabInput[]>('/simple-case/labs/pdf', { body });
}

export function uploadLabImage(file: File, rotation = 0) {
  const body = new FormData();
  body.append('file', file);
  body.append('rotation', String(rotation));
  return uploadRequest<LabInput[]>('/simple-case/labs/image', { body });
}

export function uploadReportPdf(
  file: File,
  reportType: string,
  bodyRegion: string,
) {
  const body = new FormData();
  body.append('file', file);
  body.append('report_type', reportType || 'Tıbbi Rapor');
  if (bodyRegion.trim()) body.append('body_region', bodyRegion.trim());
  return uploadRequest<MedicalReportInput>('/simple-case/reports/pdf', { body });
}

export function uploadReportImage(
  file: File,
  reportType: string,
  bodyRegion: string,
) {
  const body = new FormData();
  body.append('file', file);
  body.append('report_type', reportType || 'Tıbbi Rapor');
  if (bodyRegion.trim()) body.append('body_region', bodyRegion.trim());
  return uploadRequest<MedicalReportInput>('/simple-case/reports/image', { body });
}


export function interpretSimpleCase(
  payload: SimpleCaseRequest,
  patientId?: string | null,
) {
  const path = patientId
    ? `/simple-case/patients/${patientId}/ai-interpretation`
    : '/simple-case/ai-interpretation';
  return apiClient.post<CaseAIInterpretation>(path, payload);
}


export function getSavedSimpleCase(patientId: string) {
  return apiClient.get<SavedSimpleCase>(`/simple-case/patients/${patientId}`);
}
