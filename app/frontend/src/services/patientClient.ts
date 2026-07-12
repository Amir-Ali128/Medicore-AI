import { getAccessToken } from './authClient';
import type { ClinicalIntakeInput } from './labAnalysisClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export const ACTIVE_PATIENT_ID_KEY = 'medicore:activePatientId';
export const ACTIVE_CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';

export type PatientRecord = {
  id: string;
  external_ref: string | null;
  sex: string;
  date_of_birth: string | null;
  is_pregnant: boolean | null;
  metadata_json: {
    full_name?: string | null;
    age?: number | null;
    height_cm?: number | null;
    weight_kg?: number | null;
    clinical_context?: ClinicalIntakeInput;
    [key: string]: unknown;
  };
  created_at: string;
  updated_at: string;
};

function headers(): HeadersInit {
  const token = getAccessToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function payloadFromIntake(intake: ClinicalIntakeInput) {
  const patient = intake.patient_information;
  return {
    full_name: patient.full_name?.trim() ?? '',
    age: patient.age,
    sex: patient.sex ?? 'unknown',
    height_cm: patient.height_cm,
    weight_kg: patient.weight_kg,
    clinical_context: intake,
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

export function getActivePatientId(): string | null {
  return localStorage.getItem(ACTIVE_PATIENT_ID_KEY);
}

export async function savePatientRecord(
  intake: ClinicalIntakeInput,
): Promise<PatientRecord> {
  const activeId = getActivePatientId();
  const response = await fetch(
    activeId ? `${API_BASE_URL}/patients/${activeId}` : `${API_BASE_URL}/patients`,
    {
      method: activeId ? 'PUT' : 'POST',
      headers: headers(),
      body: JSON.stringify(payloadFromIntake(intake)),
    },
  );

  if (!response.ok) {
    throw new Error(`Hasta kaydı kaydedilemedi: ${response.status} ${await readError(response)}`);
  }

  const record = (await response.json()) as PatientRecord;
  localStorage.setItem(ACTIVE_PATIENT_ID_KEY, record.id);
  return record;
}

export async function getPatientRecord(patientId: string): Promise<PatientRecord> {
  const response = await fetch(`${API_BASE_URL}/patients/${patientId}`, {
    headers: headers(),
  });
  if (!response.ok) {
    throw new Error(`Hasta kaydı alınamadı: ${response.status} ${await readError(response)}`);
  }
  return response.json();
}

export async function listPatientRecords(): Promise<PatientRecord[]> {
  const response = await fetch(`${API_BASE_URL}/patients?limit=100`, {
    headers: headers(),
  });
  if (!response.ok) {
    throw new Error(`Hasta kayıtları alınamadı: ${response.status} ${await readError(response)}`);
  }
  return response.json();
}
