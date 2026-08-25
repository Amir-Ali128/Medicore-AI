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
    full_name?: string | null;
    age?: number | null;
    height_cm?: number | null;
    weight_kg?: number | null;
    clinical_context?: ClinicalIntakeInput;
    owner_user_id?: string;
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

function createInternalIndividualReference(): string {
  const uuid = crypto.randomUUID().replace(/-/g, '').toUpperCase();
  return `IND-${uuid.slice(0, 20)}`;
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

export function activatePatientRecord(record: PatientRecord): void {
  localStorage.setItem(ACTIVE_PATIENT_ID_KEY, record.id);
  localStorage.setItem(ACTIVE_PATIENT_PROTOCOL_KEY, record.protocol_no);

  const intake = record.metadata_json?.clinical_context;
  if (intake) {
    localStorage.setItem(ACTIVE_CLINICAL_INTAKE_KEY, JSON.stringify(intake));
  }

  const age = intake?.patient_information.age ?? record.metadata_json?.age ?? null;
  if (age !== null && age !== undefined) {
    localStorage.setItem('medicore:lastPatientAge', String(age));
  }

  const sex = intake?.patient_information.sex ?? record.sex ?? null;
  if (sex && sex !== 'unknown') {
    localStorage.setItem('medicore:lastPatientSex', String(sex));
  }

  window.dispatchEvent(
    new CustomEvent<PatientRecord>('medicore:patient-saved', {
      detail: record,
    }),
  );
}

async function sendPatientSave(
  intake: ClinicalIntakeInput,
  patientId: string | null,
  protocolNo: string,
) {
  return fetch(
    patientId ? `${API_BASE_URL}/patients/${patientId}` : `${API_BASE_URL}/patients`,
    {
      method: patientId ? 'PUT' : 'POST',
      headers: headers(),
      body: JSON.stringify(payloadFromIntake(intake, protocolNo)),
    },
  );
}

export async function savePatientRecord(
  intake: ClinicalIntakeInput,
  protocolNo?: string,
): Promise<PatientRecord> {
  const activeId = getActivePatientId();
  const existingProtocolNo = getActivePatientProtocolNo();
  let resolvedProtocolNo = normalizeProtocolNo(
    protocolNo ?? existingProtocolNo ?? createInternalIndividualReference(),
  );

  let response = await sendPatientSave(intake, activeId, resolvedProtocolNo);

  // Records created by older builds were not account-owned. If an old local
  // patient id can no longer be updated, preserve the current form by creating
  // a fresh account-owned record instead of forcing the patient to re-enter it.
  if (activeId && (response.status === 403 || response.status === 404)) {
    localStorage.removeItem(ACTIVE_PATIENT_ID_KEY);
    localStorage.removeItem(ACTIVE_PATIENT_PROTOCOL_KEY);
    resolvedProtocolNo = createInternalIndividualReference();
    response = await sendPatientSave(intake, null, resolvedProtocolNo);
  }

  if (!response.ok) {
    throw new Error(`Hasta kaydı kaydedilemedi: ${response.status} ${await readError(response)}`);
  }

  const record = (await response.json()) as PatientRecord;
  activatePatientRecord(record);
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
  activatePatientRecord(record);
  return record;
}

export async function deletePatientRecord(patientId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/patients/${patientId}`, {
    method: 'DELETE',
    headers: headers(),
  });

  if (!response.ok) {
    throw new Error(`Hasta kaydı silinemedi: ${response.status} ${await readError(response)}`);
  }

  if (getActivePatientId() === patientId) {
    localStorage.removeItem(ACTIVE_PATIENT_ID_KEY);
    localStorage.removeItem(ACTIVE_PATIENT_PROTOCOL_KEY);
    localStorage.removeItem(ACTIVE_CLINICAL_INTAKE_KEY);
  }
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
