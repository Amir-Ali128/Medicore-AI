import { getAccessToken } from './authClient';
import type { ClinicalIntakeInput } from './labAnalysisClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export const ACTIVE_PATIENT_ID_KEY = 'medicore:activePatientId';
export const ACTIVE_PATIENT_PROTOCOL_KEY = 'medicore:activePatientProtocol';
export const ACTIVE_CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';

export type PatientRecord = {
  id: string;
  protocol_no: string;
  external_ref: string | null;
  sex: string;
  date_of_birth: string | null;
  is_pregnant: boolean | null;
  metadata_json: {
    // Kept only for backward-compatible typing of older records/UI code.
    // New patient records no longer send or store a full name.
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

function normalizeProtocolNo(value: string) {
  return value.trim().toUpperCase();
}

function payloadFromIntake(intake: ClinicalIntakeInput, protocolNo: string) {
  const patient = intake.patient_information;
  return {
    protocol_no: protocolNo,
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

export function getActivePatientProtocolNo(): string | null {
  return localStorage.getItem(ACTIVE_PATIENT_PROTOCOL_KEY);
}

function rememberPatientRecord(record: PatientRecord) {
  localStorage.setItem(ACTIVE_PATIENT_ID_KEY, record.id);
  localStorage.setItem(ACTIVE_PATIENT_PROTOCOL_KEY, record.protocol_no);
  window.dispatchEvent(
    new CustomEvent<PatientRecord>('medicore:patient-saved', {
      detail: record,
    }),
  );
}

export async function savePatientRecord(
  intake: ClinicalIntakeInput,
  protocolNo?: string,
): Promise<PatientRecord> {
  const activeId = getActivePatientId();
  const resolvedProtocolNo = normalizeProtocolNo(
    protocolNo ?? getActivePatientProtocolNo() ?? '',
  );

  if (!resolvedProtocolNo) {
    throw new Error('Protokol numarasını hasta girmelidir.');
  }

  const response = await fetch(
    activeId ? `${API_BASE_URL}/patients/${activeId}` : `${API_BASE_URL}/patients`,
    {
      method: activeId ? 'PUT' : 'POST',
      headers: headers(),
      body: JSON.stringify(payloadFromIntake(intake, resolvedProtocolNo)),
    },
  );

  if (!response.ok) {
    throw new Error(`Hasta kaydı kaydedilemedi: ${response.status} ${await readError(response)}`);
  }

  const record = (await response.json()) as PatientRecord;
  rememberPatientRecord(record);
  return record;
}

export async function getPatientRecord(patientId: string): Promise<PatientRecord> {
  const response = await fetch(`${API_BASE_URL}/patients/${patientId}`, {
    headers: headers(),
  });
  if (!response.ok) {
    throw new Error(`Hasta kaydı alınamadı: ${response.status} ${await readError(response)}`);
  }
  const record = (await response.json()) as PatientRecord;
  rememberPatientRecord(record);
  return record;
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
