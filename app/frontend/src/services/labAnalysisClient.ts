import { getAccessToken } from './authClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export const LAST_ANALYSIS_RUN_ID_KEY = 'medicore:lastAnalysisRunId';
export const LAST_LAB_REPORT_ID_KEY = 'medicore:lastLabReportId';

export const LAST_PATIENT_DISPLAY_NAME_KEY = 'medicore:lastPatientDisplayName';
export const LAST_PATIENT_AGE_KEY = 'medicore:lastPatientAge';
export const LAST_PATIENT_SEX_KEY = 'medicore:lastPatientSex';
export const LAST_PATIENT_BIRTH_DATE_KEY = 'medicore:lastPatientBirthDate';

const DEMO_PATIENT_ID = '3fa85f64-5717-4562-b3fc-2c963f66afa6';
const DEMO_UPLOADED_BY_USER_ID = '3fa85f64-5717-4562-b3fc-2c963f66afa6';
const ACTIVE_PATIENT_ID_KEY = 'medicore:activePatientId';

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
  height_cm?: number | string | null;
  weight_kg?: number | string | null;
};

export type LabReportMetadata = {
  patient_display_name?: string | null;
  patient_age?: number | null;
  patient_sex?: string | null;
  patient_birth_date?: string | null;
  patient_metadata_source?: string | null;
  chief_complaint?: string | null;
  clinical_history?: string | null;
  clinical_context?: ClinicalIntakeInput | null;
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

type AnalysisRunSummary = {
  id: string;
  patient_id: string;
  lab_report_id: string;
  total_results: number;
  normal_count: number;
  low_count: number;
  high_count: number;
  needs_review_count: number;
  unknown_count: number;
  completed_at: string | null;
  created_at: string;
};

export type ManualLabOption = {
  name: string;
  default_unit: string;
  unit_options: string[];
};

export type ManualLabValueInput = {
  raw_parameter_name: string;
  normalized_value: number;
  unit: string;
  extracted_reference_min: number | null;
  extracted_reference_max: number | null;
  measured_at: string | null;
};

export type ClinicalAttachmentCategory =
  | 'laboratory'
  | 'xray'
  | 'ultrasound'
  | 'ct'
  | 'mri'
  | 'pet_ct'
  | 'pathology'
  | 'dicom'
  | 'other';

export type ClinicalAttachmentInput = {
  file_name: string;
  category: ClinicalAttachmentCategory;
  content_type: string | null;
  size_bytes: number;
  last_modified_ms: number | null;
};

export type ClinicalIntakeInput = {
  patient_information: {
    full_name: string | null;
    age: number | null;
    sex: string | null;
    height_cm: number | null;
    weight_kg: number | null;
  };
  presenting_complaint: {
    reason_for_visit: string | null;
    chief_complaint: string | null;
    complaint_duration: string | null;
    severity_score: number | null;
    associated_symptoms: string | null;
  };
  clinical_history_details: {
    history_of_present_illness: string | null;
    current_medical_conditions: string | null;
    past_medical_history: string | null;
    family_history: string | null;
    medications: string | null;
    allergies: string | null;
    tobacco_alcohol: string | null;
    past_surgeries: string | null;
  };
  physical_exam: {
    blood_pressure_systolic: number | null;
    blood_pressure_diastolic: number | null;
    pulse_bpm: number | null;
    temperature_c: number | null;
    respiratory_rate: number | null;
    oxygen_saturation_percent: number | null;
    examination_findings: string | null;
  };
  imaging_results: {
    xray: string | null;
    ultrasound: string | null;
    ct: string | null;
    mri: string | null;
    pet_ct: string | null;
    pathology: string | null;
  };
  attachments: ClinicalAttachmentInput[];
};

export type ManualLabReportInput = {
  patient_id: string;
  report_date: string;
  clinical_context: ClinicalIntakeInput;
  values: ManualLabValueInput[];
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

  // Restored archive responses do not repeat PDF demographics. Keep the
  // already stored patient profile instead of erasing it during navigation.
  if (!patient) {
    return;
  }

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

export async function saveLabReportClinicalContext(
  labReportId: string,
  clinicalContext: ClinicalIntakeInput | null | undefined,
): Promise<LabReportSummary | null> {
  if (!clinicalContext) {
    return null;
  }

  const response = await fetch(
    `${API_BASE_URL}/lab-reports/${labReportId}/clinical-context`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify(clinicalContext),
    },
  );

  if (!response.ok) {
    const errorText = await readErrorMessage(response);
    throw new Error(
      `Clinical context save failed: ${response.status} ${errorText}`,
    );
  }

  return response.json();
}

async function submitStructuredLabReport(
  payload: Record<string, unknown>,
  errorPrefix: string,
  endpoint = '/lab-analysis/mock',
): Promise<LabAnalysisResponse> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await readErrorMessage(response);
    throw new Error(`${errorPrefix}: ${response.status} ${errorText}`);
  }

  const result = (await response.json()) as LabAnalysisResponse;
  rememberLatestAnalysis(result);

  return result;
}

export async function fetchManualLabOptions(): Promise<ManualLabOption[]> {
  const response = await fetch(`${API_BASE_URL}/lab-analysis/manual-options`, {
    headers: {
      ...authHeaders(),
    },
  });

  if (!response.ok) {
    const errorText = await readErrorMessage(response);
    throw new Error(
      `Manuel laboratuvar test listesi yüklenemedi: ${response.status} ${errorText}`,
    );
  }

  const body = (await response.json()) as { parameters?: ManualLabOption[] };
  return Array.isArray(body.parameters) ? body.parameters : [];
}

export async function runBackendMockAnalysis(): Promise<LabAnalysisResponse> {
  return submitStructuredLabReport(
    {
      patient_id: DEMO_PATIENT_ID,
      uploaded_by_user_id: DEMO_UPLOADED_BY_USER_ID,
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
    },
    'Backend analysis failed',
  );
}

export async function submitManualLabResults(
  input: ManualLabReportInput,
): Promise<LabAnalysisResponse> {
  const values = input.values.map((value) => {
    const unit = value.unit.trim();

    return {
      raw_parameter_name: value.raw_parameter_name.trim(),
      raw_value: String(value.normalized_value),
      normalized_value: value.normalized_value,
      unit: unit || null,
      extracted_reference_min: value.extracted_reference_min,
      extracted_reference_max: value.extracted_reference_max,
      extracted_unit: unit || null,
      measured_at: value.measured_at || input.report_date,
    };
  });

  const context = input.clinical_context;

  return submitStructuredLabReport(
    {
      patient_id: input.patient_id,
      uploaded_by_user_id: null,
      file_name: `manual-entry-${input.report_date}.json`,
      report_date: input.report_date,
      ...context,
      chief_complaint: context.presenting_complaint.chief_complaint,
      clinical_history:
        context.clinical_history_details.history_of_present_illness,
      values,
    },
    'Manual result analysis failed',
    '/lab-analysis/manual',
  );
}

export async function uploadLabReportPdf(
  file: File,
  clinicalContext?: ClinicalIntakeInput,
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

  await Promise.all([
    saveLabReportPatientMetadata(result.lab_report_id, result.patient),
    saveLabReportClinicalContext(result.lab_report_id, clinicalContext),
  ]);
  rememberLatestAnalysis(result);

  return result;
}

export async function analyzeLabReportImage(
  file: File,
  clinicalContext?: ClinicalIntakeInput,
): Promise<LabAnalysisResponse> {
  const patientId = localStorage.getItem(ACTIVE_PATIENT_ID_KEY);
  if (!patientId) {
    throw new Error(
      'Önce Hasta Bilgileri bölümünde Kaydet’e basarak aktif hasta kaydını oluşturmalısın.',
    );
  }

  const formData = new FormData();
  formData.append('patient_id', patientId);
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/extraction/lab-report/analyze`, {
    method: 'POST',
    headers: {
      ...authHeaders(),
    },
    body: formData,
  });

  if (!response.ok) {
    const errorText = await readErrorMessage(response);
    throw new Error(`Fotoğraf analizi başarısız oldu: ${response.status} ${errorText}`);
  }

  const body = (await response.json()) as { analysis: LabAnalysisResponse };
  const result = body.analysis;

  await Promise.all([
    saveLabReportPatientMetadata(result.lab_report_id, result.patient),
    saveLabReportClinicalContext(result.lab_report_id, clinicalContext),
  ]);
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

  const rows = (await response.json()) as Array<
    LabAnalysisResult & { id?: string }
  >;

  return rows.map((row) => ({
    ...row,
    lab_result_id: row.lab_result_id ?? row.id ?? '',
  }));
}

export async function getLatestAnalysisForLabReport(
  labReportId: string,
  patientId: string,
): Promise<LabAnalysisResponse | null> {
  const response = await fetch(
    `${API_BASE_URL}/lab-reports/${labReportId}/analysis-runs`,
    { headers: { ...authHeaders() } },
  );

  if (!response.ok) {
    const errorText = await readErrorMessage(response);
    throw new Error(
      `Kayıtlı laboratuvar analizi yüklenemedi: ${response.status} ${errorText}`,
    );
  }

  const runs = (await response.json()) as AnalysisRunSummary[];
  const latestRun = [...runs].sort((left, right) => {
    const leftTime = Date.parse(left.completed_at ?? left.created_at) || 0;
    const rightTime = Date.parse(right.completed_at ?? right.created_at) || 0;
    return rightTime - leftTime;
  })[0];

  if (!latestRun) return null;

  const results = await getAnalysisRunResults(latestRun.id);
  const restored: LabAnalysisResponse = {
    analysis_run_id: latestRun.id,
    lab_report_id: latestRun.lab_report_id,
    patient_id: patientId,
    results,
    counts: {
      total: latestRun.total_results,
      normal: latestRun.normal_count,
      low: latestRun.low_count,
      high: latestRun.high_count,
      needs_review: latestRun.needs_review_count,
      unknown: latestRun.unknown_count,
    },
  };

  rememberLatestAnalysis(restored);
  return restored;
}
