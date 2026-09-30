import { API_BASE_URL, apiClient } from './apiClient';
import { getAccessToken } from './authClient';

export type SexValue = 'female' | 'male' | 'other' | 'unknown';

export type ClinicalContext = {
  age: number | null;
  sex: SexValue;
  complaints: string[];
  history: string[];
  medications: string[];
  notes: string | null;
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
  source_reference: string | null;
  source_references: LabReference[];
  source_metadata?: Record<string, unknown>;
};

export type MedicalReportInput = {
  report_type: string;
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
  clinical_summary: string;
  integrated_findings: string[];
  correlations: string[];
  attention_points: string[];
  missing_or_conflicting_data: string[];
  clinician_conclusion: string;
  limitations: string[];
  model: string;
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


export function interpretSimpleCase(payload: SimpleCaseRequest) {
  return apiClient.post<CaseAIInterpretation>(
    '/simple-case/ai-interpretation',
    payload,
  );
}
