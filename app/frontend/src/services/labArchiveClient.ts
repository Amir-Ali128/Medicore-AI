import { getAccessToken } from './authClient';
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
  const claimResponse = await fetch(`${API_BASE_URL}/lab-reports/${labReportId}/save`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ patient_id: patientId }),
  });

  if (!claimResponse.ok) {
    throw new Error(
      `Laboratuvar kaydı arşive eklenemedi: ${claimResponse.status} ${await readError(claimResponse)}`,
    );
  }

  const contextResponse = await fetch(
    `${API_BASE_URL}/lab-reports/${labReportId}/clinical-context`,
    {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify(clinicalContext),
    },
  );

  if (!contextResponse.ok) {
    throw new Error(
      `Klinik bağlam kaydedilemedi: ${contextResponse.status} ${await readError(contextResponse)}`,
    );
  }

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
    }).catch(() => undefined);
  }

  return contextResponse.json();
}

export async function uploadLabReportOriginalFile(
  labReportId: string,
  file: File,
): Promise<LabReportSummary> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/lab-reports/${labReportId}/file`, {
    method: 'POST',
    headers: authHeaders(false),
    body: formData,
  });

  if (!response.ok) {
    throw new Error(
      `PDF anonimleştirilip kaydedilemedi: ${response.status} ${await readError(response)}`,
    );
  }

  return response.json();
}

export async function openLabReportPdf(
  labReportId: string,
  fileName?: string | null,
): Promise<void> {
  const popup = window.open('', '_blank');

  try {
    const response = await fetch(`${API_BASE_URL}/lab-reports/${labReportId}/file`, {
      headers: authHeaders(false),
    });

    if (!response.ok) {
      throw new Error(
        `PDF açılamadı: ${response.status} ${await readError(response)}`,
      );
    }

    const blob = await response.blob();
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
  }
}

export async function deleteLabReport(labReportId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/lab-reports/${labReportId}`, {
    method: 'DELETE',
    headers: authHeaders(false),
  });

  if (!response.ok) {
    throw new Error(
      `Laboratuvar kaydı silinemedi: ${response.status} ${await readError(response)}`,
    );
  }
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
  return Array.isArray(reports) ? reports : [];
}
