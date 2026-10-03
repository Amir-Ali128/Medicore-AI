import { getAccessToken } from './authClient';
import { assertCurrentPatientScope, capturePatientScope } from './patientScope';
import type {
  ClinicalIntakeInput,
  LabReportSummary,
  PatientMetadata,
} from './labAnalysisClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

function authHeaders(contentType = true): HeadersInit {
  const token = getAccessToken();
  return {
    ...(contentType ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function readError(response: Response) {
  try {
    const body = await response.json();
    return typeof body?.detail === 'string' ? body.detail : JSON.stringify(body);
  } catch {
    return response.statusText;
  }
}

export async function saveLabReportToPatient(
  labReportId: string,
  patientId: string,
  clinicalContext: ClinicalIntakeInput,
  patientMetadata?: PatientMetadata | null,
): Promise<LabReportSummary> {
  const scope = capturePatientScope();
  if (scope.patientId !== patientId) throw new Error('Klinik bağlam seçilen hasta ile eşleşmiyor.');
  const claimResponse = await fetch(`${API_BASE_URL}/lab-reports/${labReportId}/save`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ patient_id: patientId }),
    signal: scope.signal,
  });

  if (!claimResponse.ok) {
    throw new Error(
      `Laboratuvar kaydı arşive eklenemedi: ${claimResponse.status} ${await readError(claimResponse)}`,
    );
  }
  const claimed = (await claimResponse.json()) as LabReportSummary;
  assertCurrentPatientScope(scope);
  if (claimed.patient_id !== patientId || claimed.id !== labReportId) throw new Error('Laboratuvar kaydı seçilen hasta/rapor ile eşleşmiyor.');

  const contextResponse = await fetch(
    `${API_BASE_URL}/lab-reports/${labReportId}/clinical-context`,
    {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify(clinicalContext),
      signal: scope.signal,
    },
  );

  if (!contextResponse.ok) {
    throw new Error(
      `Klinik bağlam kaydedilemedi: ${contextResponse.status} ${await readError(contextResponse)}`,
    );
  }
  const report = (await contextResponse.json()) as LabReportSummary;
  assertCurrentPatientScope(scope);
  if (report.patient_id !== patientId || report.id !== labReportId) throw new Error('Laboratuvar kaydı seçilen hasta/rapor ile eşleşmiyor.');

  if (patientMetadata) {
    await fetch(`${API_BASE_URL}/lab-reports/${labReportId}/patient-metadata`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({
        display_name: null,
        age: patientMetadata.age ?? null,
        sex: patientMetadata.sex ?? null,
        birth_date: null,
      }),
      signal: scope.signal,
    }).catch(() => undefined);
  }

  assertCurrentPatientScope(scope);
  return report;
}

export async function uploadLabReportOriginalFile(
  labReportId: string,
  file: File,
): Promise<LabReportSummary> {
  const scope = capturePatientScope();
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/lab-reports/${labReportId}/file`, {
    method: 'POST',
    headers: authHeaders(false),
    body: formData,
    signal: scope.signal,
  });

  if (!response.ok) {
    throw new Error(
      `PDF anonimleştirilip kaydedilemedi: ${response.status} ${await readError(response)}`,
    );
  }

  const report = (await response.json()) as LabReportSummary;
  assertCurrentPatientScope(scope);
  if (report.id !== labReportId || (scope.patientId && report.patient_id !== scope.patientId)) throw new Error('Laboratuvar dosyası seçilen hasta/rapor ile eşleşmiyor.');
  return report;
}

export async function openLabReportPdf(
  labReportId: string,
  fileName?: string | null,
): Promise<void> {
  const scope = capturePatientScope();
  const popup = window.open('', '_blank');
  const closePopup = () => popup?.close();
  scope.signal.addEventListener('abort', closePopup, { once: true });

  try {
    const response = await fetch(`${API_BASE_URL}/lab-reports/${labReportId}/file`, {
      headers: authHeaders(false),
      signal: scope.signal,
    });

    if (!response.ok) {
      throw new Error(
        `PDF açılamadı: ${response.status} ${await readError(response)}`,
      );
    }

    const blob = await response.blob();
    assertCurrentPatientScope(scope);
    const objectUrl = URL.createObjectURL(
      blob.type ? blob : new Blob([blob], { type: 'application/pdf' }),
    );

    if (popup) {
      popup.document.title = fileName || 'Laboratuvar PDF';
      popup.location.href = objectUrl;
    } else {
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.target = '_blank';
      anchor.rel = 'noopener noreferrer';
      anchor.click();
    }

    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  } catch (error) {
    popup?.close();
    throw error;
  } finally {
    scope.signal.removeEventListener('abort', closePopup);
  }
}

export async function deleteLabReport(labReportId: string): Promise<void> {
  const scope = capturePatientScope();
  const response = await fetch(`${API_BASE_URL}/lab-reports/${labReportId}`, {
    method: 'DELETE',
    headers: authHeaders(false),
    signal: scope.signal,
  });

  if (!response.ok) {
    throw new Error(
      `Laboratuvar kaydı silinemedi: ${response.status} ${await readError(response)}`,
    );
  }
  assertCurrentPatientScope(scope);
}

export async function listPatientLabReports(patientId: string): Promise<LabReportSummary[]> {
  const response = await fetch(`${API_BASE_URL}/patients/${patientId}/lab-reports`, {
    headers: authHeaders(false),
  });

  if (!response.ok) {
    throw new Error(
      `Laboratuvar arşivi yüklenemedi: ${response.status} ${await readError(response)}`,
    );
  }

  const reports = (await response.json()) as LabReportSummary[];
  if (Array.isArray(reports) && reports.some((report) => report.patient_id !== patientId)) throw new Error('Laboratuvar listesi seçilen hasta ile eşleşmiyor.');
  return Array.isArray(reports) ? reports : [];
}
