import { getAccessToken } from './authClient';
import {
  LAST_ANALYSIS_RUN_ID_KEY,
  LAST_LAB_REPORT_ID_KEY,
  LAST_PATIENT_AGE_KEY,
  LAST_PATIENT_DISPLAY_NAME_KEY,
  LAST_PATIENT_SEX_KEY,
  type ClinicalIntakeInput,
  type LabAnalysisResponse,
} from './labAnalysisClient';
import {
  LAST_RADIOLOGY_REPORT_ID_KEY,
  type RadiologyReport,
} from './radiologyClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

const ACTIVE_CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';

export type CombinedCaseSectionSummary = {
  clinical_characters: number;
  laboratory_characters: number;
  radiology_characters: number;
  parsed_lab_values: number;
};

export type CombinedCaseImportResponse = {
  clinical_context: ClinicalIntakeInput;
  lab_analysis: LabAnalysisResponse;
  radiology_report: RadiologyReport;
  sections: CombinedCaseSectionSummary;
  warnings: string[];
};

function authHeaders(): HeadersInit {
  const token = getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function readErrorMessage(response: Response): Promise<string> {
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    try {
      const body = await response.json();
      return typeof body?.detail === 'string' ? body.detail : JSON.stringify(body);
    } catch {
      return response.statusText;
    }
  }
  return response.text();
}

function rememberCombinedCase(result: CombinedCaseImportResponse): void {
  localStorage.setItem(
    LAST_ANALYSIS_RUN_ID_KEY,
    result.lab_analysis.analysis_run_id,
  );
  localStorage.setItem(
    LAST_LAB_REPORT_ID_KEY,
    result.lab_analysis.lab_report_id,
  );
  localStorage.setItem(
    LAST_RADIOLOGY_REPORT_ID_KEY,
    result.radiology_report.id,
  );
  localStorage.setItem(
    ACTIVE_CLINICAL_INTAKE_KEY,
    JSON.stringify(result.clinical_context),
  );

  const patient = result.clinical_context.patient_information;
  if (patient.full_name) {
    localStorage.setItem(LAST_PATIENT_DISPLAY_NAME_KEY, patient.full_name);
  } else {
    localStorage.removeItem(LAST_PATIENT_DISPLAY_NAME_KEY);
  }

  if (patient.age !== null) {
    localStorage.setItem(LAST_PATIENT_AGE_KEY, String(patient.age));
  } else {
    localStorage.removeItem(LAST_PATIENT_AGE_KEY);
  }

  if (patient.sex) {
    localStorage.setItem(LAST_PATIENT_SEX_KEY, patient.sex);
  } else {
    localStorage.removeItem(LAST_PATIENT_SEX_KEY);
  }
}

export async function uploadCombinedCasePdf(
  file: File,
): Promise<CombinedCaseImportResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/combined-case/upload`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });

  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new Error(`Birleşik vaka PDF aktarımı başarısız: ${response.status} ${message}`);
  }

  const result = (await response.json()) as CombinedCaseImportResponse;
  rememberCombinedCase(result);
  return result;
}
