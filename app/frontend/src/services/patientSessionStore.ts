export const PATIENT_HISTORY_KEY = 'medicore:patientHistory';

const ACTIVE_PATIENT_KEYS = [
  'medicore:lastAnalysisRunId',
  'medicore:lastLabReportId',
  'medicore:lastRadiologyReportId',
  'medicore:lastPatientDisplayName',
  'medicore:lastPatientAge',
  'medicore:lastPatientSex',
  'medicore:lastPatientBirthDate',
] as const;

export type PatientHistoryRecord = {
  id: string;
  archivedAt: string;
  displayName: string;
  age: string | null;
  sex: string | null;
  birthDate: string | null;
  analysisRunId: string | null;
  labReportId: string | null;
  radiologyReportId: string | null;
  snapshot: Record<string, string>;
};

function readHistory(): PatientHistoryRecord[] {
  try {
    const raw = localStorage.getItem(PATIENT_HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function getFirstStoredValue(keys: string[]) {
  for (const key of keys) {
    const value = localStorage.getItem(key)?.trim();
    if (value) return value;
  }
  return null;
}

function collectActiveSnapshot() {
  const snapshot: Record<string, string> = {};
  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index);
    if (!key || !key.startsWith('medicore:last')) continue;
    const value = localStorage.getItem(key);
    if (value !== null) snapshot[key] = value;
  }
  return snapshot;
}

export function getPatientHistory() {
  return readHistory().sort(
    (first, second) =>
      new Date(second.archivedAt).getTime() - new Date(first.archivedAt).getTime(),
  );
}

export function hasActivePatientSession() {
  return ACTIVE_PATIENT_KEYS.some((key) => Boolean(localStorage.getItem(key)));
}

export function archiveActivePatientSession(): PatientHistoryRecord | null {
  const snapshot = collectActiveSnapshot();
  if (Object.keys(snapshot).length === 0) return null;

  const record: PatientHistoryRecord = {
    id: crypto.randomUUID(),
    archivedAt: new Date().toISOString(),
    displayName:
      getFirstStoredValue([
        'medicore:lastPatientDisplayName',
        'medicore:last_patient_display_name',
      ]) ?? 'İsimsiz hasta',
    age: getFirstStoredValue([
      'medicore:lastPatientAge',
      'medicore:last_patient_age',
    ]),
    sex: getFirstStoredValue([
      'medicore:lastPatientSex',
      'medicore:last_patient_sex',
    ]),
    birthDate: getFirstStoredValue([
      'medicore:lastPatientBirthDate',
      'medicore:last_patient_birth_date',
    ]),
    analysisRunId: localStorage.getItem('medicore:lastAnalysisRunId'),
    labReportId: localStorage.getItem('medicore:lastLabReportId'),
    radiologyReportId: localStorage.getItem('medicore:lastRadiologyReportId'),
    snapshot,
  };

  const history = readHistory();
  history.unshift(record);
  localStorage.setItem(PATIENT_HISTORY_KEY, JSON.stringify(history.slice(0, 100)));
  return record;
}

export function clearActivePatientSession() {
  const keysToRemove: string[] = [];
  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index);
    if (key?.startsWith('medicore:last')) keysToRemove.push(key);
  }
  keysToRemove.forEach((key) => localStorage.removeItem(key));
}

export function startNewPatientSession() {
  archiveActivePatientSession();
  clearActivePatientSession();
}

export function restorePatientSession(recordId: string) {
  const record = readHistory().find((item) => item.id === recordId);
  if (!record) return false;
  clearActivePatientSession();
  Object.entries(record.snapshot).forEach(([key, value]) => {
    localStorage.setItem(key, value);
  });
  return true;
}

export function deletePatientHistoryRecord(recordId: string) {
  const next = readHistory().filter((item) => item.id !== recordId);
  localStorage.setItem(PATIENT_HISTORY_KEY, JSON.stringify(next));
}
