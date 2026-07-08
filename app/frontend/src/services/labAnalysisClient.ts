import { getAccessToken } from './authClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export const LAST_ANALYSIS_RUN_ID_KEY = 'medicore:lastAnalysisRunId';
export const LAST_LAB_REPORT_ID_KEY = 'medicore:lastLabReportId';

export const LAST_PATIENT_DISPLAY_NAME_KEY = 'medicore:lastPatientDisplayName';
export const LAST_PATIENT_AGE_KEY = 'medicore:lastPatientAge';
export const LAST_PATIENT_SEX_KEY = 'medicore:lastPatientSex';
export const LAST_PATIENT_BIRTH_DATE_KEY = 'medicore:lastPatientBirthDate';

export type LabResultStatus =
  | 'normal'
  | 'low'
  | 'high'
  | 'unknown'
  | 'needs_review';

export type PatientMetadata = {
  display_name: string | null;
  age: number | null;
  sex: string | null;
  birth_date: string | null;
};

export type LabReportMetadata = {
  patient_display_name?: string | null;
  patient_age?: number | null;
  patient_sex?: string | null;
  patient_birth_date?: string | null;
  patient_metadata_source?: string | null;
  [key: string]: unknown;
};

export type LabReportSummary = {
  id: string;
  patient_id: string;
  uploaded_by_user_id: string | null;
  source_type: string;
  file_name: string | null;
  report_date: string | null;
  status: string;
  metadata_json: LabReportMetadata;
  created_at: string;
  updated_at: string;
};

export type LabAnalysisResult = {
  lab_result_id: string;
  raw_parameter_name: string;
  parameter_id: string | null;
  parameter_code: string | null;
  canonical_name: string | null;
  normalized_value: string;
  unit: string;
  reference_min: string | null;
  reference_max: string | null;
  result_status: LabResultStatus;
  trend_status: string;
  needs_review: boolean;
  reason: string;
  alias_confidence: number;
  reference_confidence: number;
  classification_confidence: number;
  trend_confidence: number;
};

export type LabAnalysisResponse = {
  analysis_run_id: string;
  lab_report_id: string;
  patient_id: string;
  patient?: PatientMetadata | null;
  results: LabAnalysisResult[];
  counts: {
    total: number;
    normal: number;
    low: number;
    high: number;
    needs_review: number;
    unknown: number;
  };
};

function authHeaders(): HeadersInit {
  const token = getAccessToken();

  return {
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

function hasPatientMetadata(patient: PatientMetadata | null | undefined): boolean {
  if (!patient) {
    return false;
  }

  const hasDisplayName = Boolean(patient.display_name);
  const hasAge = patient.age !== null && patient.age !== undefined;
  const hasSex = Boolean(patient.sex);
  const hasBirthDate = Boolean(patient.birth_date);

  return hasDisplayName || hasAge || hasSex || hasBirthDate;
}

function rememberPatientMetadata(response: LabAnalysisResponse): void {
  const patient = response.patient;

  if (patient?.display_name) {
    localStorage.setItem(
      LAST_PATIENT_DISPLAY_NAME_KEY,
      patient.display_name,
    );
  } else {
    localStorage.removeItem(LAST_PATIENT_DISPLAY_NAME_KEY);
  }

  if (patient?.age !== null && patient?.age !== undefined) {
    localStorage.setItem(LAST_PATIENT_AGE_KEY, String(patient.age));
  } else {
    localStorage.removeItem(LAST_PATIENT_AGE_KEY);
  }

  if (patient?.sex) {
    localStorage.setItem(LAST_PATIENT_SEX_KEY, patient.sex);
  } else {
    localStorage.removeItem(LAST_PATIENT_SEX_KEY);
  }

  if (patient?.birth_date) {
    localStorage.setItem(LAST_PATIENT_BIRTH_DATE_KEY, patient.birth_date);
  } else {
    localStorage.removeItem(LAST_PATIENT_BIRTH_DATE_KEY);
  }
}

export function rememberLatestAnalysis(response: LabAnalysisResponse): void {
  localStorage.setItem(LAST_ANALYSIS_RUN_ID_KEY, response.analysis_run_id);
  localStorage.setItem(LAST_LAB_REPORT_ID_KEY, response.lab_report_id);
  rememberPatientMetadata(response);
}

export async function saveLabReportPatientMetadata(
  labReportId: string,
  patient: PatientMetadata | null | undefined,
): Promise<LabReportSummary | null> {
  if (!hasPatientMetadata(patient)) {
    return null;
  }

  const response = await fetch(
    `${API_BASE_URL}/lab-reports/${labReportId}/patient-metadata`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify({
        display_name: patient?.display_name ?? null,
        age: patient?.age ?? null,
        sex: patient?.sex ?? null,
        birth_date: patient?.birth_date ?? null,
      }),
    },
  );

  if (!response.ok) {
    const errorText = await readErrorMessage(response);
    throw new Error(
      `Patient metadata save failed: ${response.status} ${errorText}`,
    );
  }

  return response.json();
}

export async function runBackendMockAnalysis(): Promise<LabAnalysisResponse> {
  const response = await fetch(`${API_BASE_URL}/lab-analysis/mock`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
    },
    body: JSON.stringify({
      patient_id: '3fa85f64-5717-4562-b3fc-2c963f66afa6',
      uploaded_by_user_id: '3fa85f64-5717-4562-b3fc-2c963f66afa6',
      file_name: 'demo-cbc.pdf',
      report_date: '2026-07-06',
      values: [
        {
          raw_parameter_name: 'Hemoglobin',
          raw_value: '12.1',
          normalized_value: 12.1,
          unit: 'g/dL',
          extracted_reference_min: 13.5,
          extracted_reference_max: 17.5,
          extracted_unit: 'g/dL',
          measured_at: '2026-07-06',
        },
      ],
    }),
  });

  if (!response.ok) {
    const errorText = await readErrorMessage(response);
    throw new Error(`Backend analysis failed: ${response.status} ${errorText}`);
  }

  const result = (await response.json()) as LabAnalysisResponse;
  rememberLatestAnalysis(result);

  return result;
}

export async function uploadLabReportPdf(
  file: File,
): Promise<LabAnalysisResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/lab-analysis/upload`, {
    method: 'POST',
    headers: {
      ...authHeaders(),
    },
    body: formData,
  });

  if (!response.ok) {
    const errorText = await readErrorMessage(response);
    throw new Error(`PDF upload analysis failed: ${response.status} ${errorText}`);
  }

  const result = (await response.json()) as LabAnalysisResponse;

  await saveLabReportPatientMetadata(result.lab_report_id, result.patient);
  rememberLatestAnalysis(result);

  return result;
}

export async function getAnalysisRunResults(
  analysisRunId: string,
): Promise<LabAnalysisResult[]> {
  const response = await fetch(
    `${API_BASE_URL}/analysis-runs/${analysisRunId}/results`,
    {
      headers: {
        ...authHeaders(),
      },
    },
  );

  if (!response.ok) {
    const errorText = await readErrorMessage(response);
    throw new Error(`Results fetch failed: ${response.status} ${errorText}`);
  }

  return response.json();
}
