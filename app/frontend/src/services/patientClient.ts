import { getAccessToken } from './authClient';
import type { ClinicalIntakeInput } from './labAnalysisClient';
import type { ClinicalContext } from './simpleCaseClient';
import { legacyClinicalIntake, normalizeClinical, recordClinical } from './clinicalRecord';
import { assertCurrentPatientScope, capturePatientScope, clearPatientScope, forgetPatientScope, isCurrentPatientScope, selectPatientScope, type PatientScope } from './patientScope';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export const ACTIVE_PATIENT_ID_KEY = 'medicore:activePatientId';
export const ACTIVE_PATIENT_PROTOCOL_KEY = 'medicore:activePatientProtocol';
export const ACTIVE_CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';
const SYNCED_CLINICAL_DRAFT_KEY = 'medicore:syncedClinicalDraft';

export type PatientRecord = {
  id: string;
  protocol_no: string;
  external_ref: string | null;
  sex: string;
  date_of_birth: string | null;
  is_pregnant: boolean | null;
  clinical?: ClinicalContext;
  metadata_json: {
    full_name?: string | null;
    age?: number | null;
    height_cm?: number | null;
    weight_kg?: number | null;
    clinical_context?: ClinicalIntakeInput | ClinicalContext;
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
  const { vital_signs: previousVitals, ...legacyFields } = intake;
  const vitals = normalizeClinical(legacyFields).vital_signs;
  if (vitals) vitals.glucose_mg_dl = previousVitals?.glucose_mg_dl ?? null;
  return {
    protocol_no: protocolNo,
    age: patient.age,
    sex: patient.sex ?? 'unknown',
    height_cm: patient.height_cm,
    weight_kg: patient.weight_kg,
    clinical_context: {
      ...intake,
      vital_signs: vitals,
    },
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

function readActiveClinicalDraft(): ClinicalIntakeInput | null {
  try {
    const raw = localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as ClinicalIntakeInput;
  } catch {
    return null;
  }
}

export function getActivePatientId(): string | null {
  return localStorage.getItem(ACTIVE_PATIENT_ID_KEY);
}

export function getActivePatientProtocolNo(): string | null {
  return localStorage.getItem(ACTIVE_PATIENT_PROTOCOL_KEY);
}

/**
 * Start a completely fresh patient workflow.
 *
 * Clearing analysis/report pointers here is important: otherwise a new patient
 * can accidentally inherit the previous patient's active analysis state in the
 * UI even though the backend records are correctly separated.
 */
export function clearActivePatientRecord(): void {
  clearPatientScope();
  window.dispatchEvent(new CustomEvent('medicore:patient-cleared'));
  window.dispatchEvent(new CustomEvent('medicore:case-summary-updated'));
}

export function setActiveClinicalDraft(patientId: string, protocolNo: string, clinical: ClinicalContext): void {
  selectPatientScope(patientId);
  const previous = readActiveClinicalDraft();
  localStorage.setItem(ACTIVE_PATIENT_PROTOCOL_KEY, protocolNo);
  const draft = JSON.stringify(legacyClinicalIntake(clinical, previous));
  localStorage.setItem(ACTIVE_CLINICAL_INTAKE_KEY, draft);
  localStorage.setItem(SYNCED_CLINICAL_DRAFT_KEY, draft);
  if (clinical.age !== null) localStorage.setItem('medicore:lastPatientAge', String(clinical.age));
  else localStorage.removeItem('medicore:lastPatientAge');
  if (clinical.sex !== 'unknown') localStorage.setItem('medicore:lastPatientSex', clinical.sex);
  else localStorage.removeItem('medicore:lastPatientSex');
}

export function activatePatientRecord(record: PatientRecord): void {
  selectPatientScope(record.id);
  localStorage.setItem(ACTIVE_PATIENT_PROTOCOL_KEY, record.protocol_no);

  const intake = legacyClinicalIntake(recordClinical(record), record.metadata_json?.clinical_context);
  if (intake) {
    const draft = JSON.stringify(intake);
    localStorage.setItem(ACTIVE_CLINICAL_INTAKE_KEY, draft);
    localStorage.setItem(SYNCED_CLINICAL_DRAFT_KEY, draft);
  } else {
    localStorage.removeItem(ACTIVE_CLINICAL_INTAKE_KEY);
  }

  const age = intake?.patient_information.age ?? record.metadata_json?.age ?? null;
  if (age !== null && age !== undefined) {
    localStorage.setItem('medicore:lastPatientAge', String(age));
  } else {
    localStorage.removeItem('medicore:lastPatientAge');
  }

  const sex = intake?.patient_information.sex ?? record.sex ?? null;
  if (sex && sex !== 'unknown') {
    localStorage.setItem('medicore:lastPatientSex', String(sex));
  } else {
    localStorage.removeItem('medicore:lastPatientSex');
  }
  if (record.date_of_birth) localStorage.setItem('medicore:lastPatientBirthDate', record.date_of_birth);
  else localStorage.removeItem('medicore:lastPatientBirthDate');

  window.dispatchEvent(
    new CustomEvent<PatientRecord>('medicore:patient-saved', {
      detail: record,
    }),
  );
  window.dispatchEvent(new CustomEvent('medicore:case-summary-updated'));
}

async function sendPatientSave(
  intake: ClinicalIntakeInput,
  patientId: string | null,
  protocolNo: string,
  scope: PatientScope,
) {
  return fetch(
    patientId ? `${API_BASE_URL}/patients/${patientId}` : `${API_BASE_URL}/patients`,
    {
      method: patientId ? 'PUT' : 'POST',
      headers: headers(),
      signal: scope.signal,
      body: JSON.stringify(payloadFromIntake(intake, protocolNo)),
    },
  );
}

/**
 * Persist the browser draft for the currently active patient before another
 * screen (especially the archive) reads patient records.
 *
 * ClinicalIntakeForm writes every field edit to localStorage immediately, while
 * the explicit Save button writes to the backend. Without this bridge a user can
 * edit the patient, open the archive, and still see the older backend snapshot.
 * This best-effort sync closes that gap without creating a new patient record.
 */
export async function syncActivePatientDraft(): Promise<PatientRecord | null> {
  const scope = capturePatientScope();
  const activeId = getActivePatientId();
  const protocolNo = getActivePatientProtocolNo();
  const draft = readActiveClinicalDraft();

  if (!activeId || !protocolNo || !draft) return null;
  if (localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY) === localStorage.getItem(SYNCED_CLINICAL_DRAFT_KEY)) return null;

  try {
    const response = await sendPatientSave(
      draft,
      activeId,
      normalizeProtocolNo(protocolNo),
      scope,
    );

    // A background archive sync must never create a replacement patient if the
    // active id is stale or inaccessible. The normal explicit Save flow handles
    // that recovery path.
    if (!response.ok) return null;

    const record = (await response.json()) as PatientRecord;
    if (!isCurrentPatientScope(scope) || record.id !== activeId) return null;
    // An older background response must not overwrite edits made while saving.
    if (JSON.stringify(draft) !== localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY)) return record;
    localStorage.setItem(SYNCED_CLINICAL_DRAFT_KEY, JSON.stringify(draft));
    return record;
  } catch {
    // Archive loading remains usable when a best-effort draft sync is offline.
    return null;
  }
}

export async function savePatientRecord(
  intake: ClinicalIntakeInput,
  protocolNo?: string,
): Promise<PatientRecord> {
  const scope = capturePatientScope();
  const activeId = getActivePatientId();
  const existingProtocolNo = getActivePatientProtocolNo();
  let resolvedProtocolNo = normalizeProtocolNo(
    protocolNo ?? existingProtocolNo ?? createInternalIndividualReference(),
  );
  let replacingInaccessibleRecord = false;

  let response = await sendPatientSave(intake, activeId, resolvedProtocolNo, scope);
  assertCurrentPatientScope(scope);

  // Records created by older builds were not account-owned. If an old local
  // patient id can no longer be updated, preserve the current form by creating
  // a fresh account-owned record instead of forcing the patient to re-enter it.
  if (activeId && (response.status === 403 || response.status === 404)) {
    replacingInaccessibleRecord = true;
    resolvedProtocolNo = createInternalIndividualReference();
    response = await sendPatientSave(intake, null, resolvedProtocolNo, scope);
  }

  if (!response.ok) {
    throw new Error(`Hasta kaydı kaydedilemedi: ${response.status} ${await readError(response)}`);
  }

  const record = (await response.json()) as PatientRecord;
  assertCurrentPatientScope(scope);
  if (activeId && record.id !== activeId && !replacingInaccessibleRecord) {
    throw new Error('Hasta kaydı yanıtı beklenen hasta ile eşleşmiyor.');
  }
  activatePatientRecord(record);
  return record;
}

export async function getPatientRecord(patientId: string, signal?: AbortSignal): Promise<PatientRecord> {
  const response = await fetch(`${API_BASE_URL}/patients/${patientId}`, {
    headers: headers(),
    signal,
  });
  if (!response.ok) {
    throw new Error(`Hasta kaydı alınamadı: ${response.status} ${await readError(response)}`);
  }
  const record = (await response.json()) as PatientRecord;
  if (record.id !== patientId) throw new Error('Hasta kaydı yanıtı beklenen hasta ile eşleşmiyor.');
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

  forgetPatientScope(patientId);
}

export async function listPatientRecords(limit = 500): Promise<PatientRecord[]> {
  // Make sure the archive reads the newest clinical draft, even if the user
  // navigated away before pressing the explicit update button.
  await syncActivePatientDraft();

  const safeLimit = Math.max(1, Math.min(limit, 500));
  const response = await fetch(`${API_BASE_URL}/patients?limit=${safeLimit}`, {
    headers: headers(),
  });
  if (!response.ok) {
    throw new Error(`Hasta kayıtları alınamadı: ${response.status} ${await readError(response)}`);
  }
  return response.json();
}
