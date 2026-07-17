import { getAccessToken } from './authClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export const DEMO_PATIENT_ID = '3fa85f64-5717-4562-b3fc-2c963f66afa6';
const DEMO_UPLOADED_BY_USER_ID = '3fa85f64-5717-4562-b3fc-2c963f66afa6';
export const ACTIVE_PATIENT_ID_KEY = 'medicore:activePatientId';
export const LAST_RADIOLOGY_REPORT_ID_KEY = 'medicore:lastRadiologyReportId';

export type RadiologyFinding = {
  text: string;
  classification: 'critical' | 'abnormal' | 'observation' | string;
  is_critical: boolean;
  matched_terms: string[];
};

export type RadiologyMeasurement = {
  value: string;
  unit: string;
  context: string;
};

export type DexaMetric = {
  site: string;
  bmd: number | null;
  bmd_unit: string | null;
  t_score: number | null;
  z_score: number | null;
  t_score_band: string | null;
  z_score_band: string | null;
  report_classification: string | null;
  context: string;
};

export type RadiologyReport = {
  id: string;
  patient_id: string;
  uploaded_by_user_id: string | null;
  source_type: string;
  file_name: string | null;
  report_date: string | null;
  modality: string;
  body_part: string;
  original_text: string;
  findings: RadiologyFinding[];
  measurements: RadiologyMeasurement[];
  dexa_metrics: DexaMetric[];
  critical_findings: string[];
  impression: string | null;
  summary: string;
  status: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type RadiologyReportInput = {
  reportDate: string | null;
  modality: string | null;
  bodyPart: string | null;
  reportText: string;
};

export function getActiveRadiologyPatientId(): string {
  return localStorage.getItem(ACTIVE_PATIENT_ID_KEY) ?? DEMO_PATIENT_ID;
}

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

function normalizeReport(report: RadiologyReport): RadiologyReport {
  return {
    ...report,
    modality: report.modality || 'UNKNOWN',
    body_part: report.body_part || 'OTHER',
    original_text: report.original_text || '',
    summary: report.summary || 'Rapor özeti oluşturulamadı.',
    findings: Array.isArray(report.findings) ? report.findings : [],
    measurements: Array.isArray(report.measurements) ? report.measurements : [],
    dexa_metrics: Array.isArray(report.dexa_metrics) ? report.dexa_metrics : [],
    critical_findings: Array.isArray(report.critical_findings)
      ? report.critical_findings
      : [],
    metadata_json:
      report.metadata_json && typeof report.metadata_json === 'object'
        ? report.metadata_json
        : {},
  };
}

async function parseReportResponse(response: Response): Promise<RadiologyReport> {
  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new Error(`Radyoloji analizi başarısız: ${response.status} ${message}`);
  }
  const report = normalizeReport((await response.json()) as RadiologyReport);
  localStorage.setItem(LAST_RADIOLOGY_REPORT_ID_KEY, report.id);
  return report;
}

export async function createManualRadiologyReport(
  input: RadiologyReportInput,
): Promise<RadiologyReport> {
  const response = await fetch(`${API_BASE_URL}/radiology-reports/manual`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
    },
    body: JSON.stringify({
      patient_id: getActiveRadiologyPatientId(),
      uploaded_by_user_id: DEMO_UPLOADED_BY_USER_ID,
      report_date: input.reportDate,
      modality: input.modality,
      body_part: input.bodyPart,
      report_text: input.reportText,
      file_name: null,
      metadata_json: { source: 'radiology_workspace' },
    }),
  });
  return parseReportResponse(response);
}

export async function uploadRadiologyReportPdf(
  file: File,
  input: Omit<RadiologyReportInput, 'reportText'>,
): Promise<RadiologyReport> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('patient_id', getActiveRadiologyPatientId());
  formData.append('uploaded_by_user_id', DEMO_UPLOADED_BY_USER_ID);
  if (input.reportDate) formData.append('report_date', input.reportDate);
  if (input.modality) formData.append('modality', input.modality);
  if (input.bodyPart) formData.append('body_part', input.bodyPart);

  const response = await fetch(`${API_BASE_URL}/radiology-reports/upload`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });
  return parseReportResponse(response);
}

export async function listPatientRadiologyReports(
  patientId = getActiveRadiologyPatientId(),
): Promise<RadiologyReport[]> {
  const response = await fetch(
    `${API_BASE_URL}/radiology-reports/patient/${patientId}?limit=50`,
    { headers: authHeaders() },
  );
  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new Error(`Radyoloji geçmişi yüklenemedi: ${response.status} ${message}`);
  }
  const reports = (await response.json()) as RadiologyReport[];
  return Array.isArray(reports) ? reports.map(normalizeReport) : [];
}
