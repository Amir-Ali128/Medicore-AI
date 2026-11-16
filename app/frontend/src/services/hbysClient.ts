import { apiClient } from './apiClient';
import { createPatient, saveSimpleCase, type SexValue, type SimpleCaseRequest } from './simpleCaseClient';

export type HbysStatus = {
  configured: boolean;
  reachable: boolean;
  software?: string | null;
  fhir_version?: string | null;
  detail?: string;
};

export type HbysEncounter = {
  encounter_id: string;
  protocol_no: string;
  department: string | null;
  admitted_at: string | null;
  status: 'in-progress' | 'finished' | string | null;
  lab_count: number;
  radiology_count: number;
  medicore_patient_id: string | null;
  hbys_export?: HbysExport | null;
};

export type HbysExport = {
  status: 'sent' | 'skipped' | 'failed' | string;
  trigger?: 'auto' | 'manual' | string;
  detail?: string;
  sent_at?: string;
  at?: string;
};

export type HbysImportedCase = {
  encounter_id: string;
  protocol_no: string;
  age: number | null;
  sex: SexValue;
  case: SimpleCaseRequest;
  redaction_counts: Record<string, number>;
  medicore_patient_id: string | null;
};

export function getHbysStatus(signal?: AbortSignal) {
  return apiClient.get<HbysStatus>('/hbys/status', { signal });
}

export function listHbysEncounters(signal?: AbortSignal) {
  return apiClient.get<HbysEncounter[]>('/hbys/encounters', { signal });
}

export function getHbysCase(encounterId: string, signal?: AbortSignal) {
  return apiClient.get<HbysImportedCase>(`/hbys/encounters/${encodeURIComponent(encounterId)}/case`, { signal });
}

export function sendHbysReport(encounterId: string, patientId: string, signal?: AbortSignal) {
  return apiClient.post<{ status: string; hbys_report: string | null; sent_at: string }>(
    `/hbys/encounters/${encodeURIComponent(encounterId)}/report`,
    { patient_id: patientId },
    { signal },
  );
}

/**
 * Import one HBYS visit into Medicore through the normal case APIs, so every
 * existing validation and privacy rule applies. Re-importing an already linked
 * visit refreshes that patient's case instead of creating a duplicate.
 */
export async function importHbysEncounter(encounterId: string, signal?: AbortSignal): Promise<string> {
  const imported = await getHbysCase(encounterId, signal);
  let patientId = imported.medicore_patient_id;
  if (!patientId) {
    const patient = await createPatient({
      protocol_no: imported.protocol_no,
      age: imported.age,
      sex: imported.sex,
      clinical_context: imported.case.clinical as unknown as Record<string, unknown>,
    }, signal);
    patientId = patient.id;
  }
  await saveSimpleCase(patientId, imported.case, signal);
  return patientId;
}
