import { getAccessToken } from './authClient';
import {
  rememberLatestAnalysis,
  saveLabReportClinicalContext,
  saveLabReportPatientMetadata,
  type ClinicalIntakeInput,
  type LabAnalysisResponse,
} from './labAnalysisClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return typeof body?.detail === 'string' ? body.detail : JSON.stringify(body);
  } catch {
    return response.statusText || 'İstek başarısız oldu.';
  }
}

export async function uploadLabReportPdfDirect(
  file: File,
  clinicalContext?: ClinicalIntakeInput,
): Promise<LabAnalysisResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const token = getAccessToken();
  const response = await fetch(`${API_BASE_URL}/lab-analysis/upload-direct`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: formData,
  });

  if (!response.ok) {
    throw new Error(
      `PDF analizi başarısız oldu: ${response.status} ${await readErrorMessage(response)}`,
    );
  }

  const result = (await response.json()) as LabAnalysisResponse;

  await Promise.all([
    saveLabReportPatientMetadata(result.lab_report_id, result.patient),
    saveLabReportClinicalContext(result.lab_report_id, clinicalContext),
  ]);
  rememberLatestAnalysis(result);

  return result;
}
