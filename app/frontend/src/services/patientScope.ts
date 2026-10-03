// Legacy screens read these active keys. Their values are a compatibility view
// of one patient's snapshot, never a shared cache across patients.
export const PATIENT_SCOPE_CHANGED_EVENT = 'medicore:patient-scope-changed';
export const ACTIVE_PATIENT_KEY = 'medicore:activePatientId';
const SNAPSHOT_PREFIX = 'medicore:patient-session:';
const OWNER_KEY = 'medicore:patientSessionOwner';
export const PATIENT_SESSION_KEYS = [
  'medicore:activePatientProtocol', 'medicore:activeClinicalIntake',
  'medicore:syncedClinicalDraft', 'medicore:lastAnalysisRunId',
  'medicore:lastLabReportId', 'medicore:lastRadiologyReportId',
  'medicore:lastPatientAge', 'medicore:lastPatientSex',
  'medicore:lastPatientBirthDate', 'medicore:lastPatientDisplayName',
  'medicore:last_patient_age', 'medicore:last_patient_sex',
  'medicore:last_patient_birth_date', 'medicore:last_patient_display_name',
  'medicore:lastCombinedReview', 'medicore:lastCombinedReviewScope',
] as const;
let generation = 0;
let controller = new AbortController();
const listeners = new Set<() => void>();

function userId(): string {
  try {
    const user = JSON.parse(localStorage.getItem('medicore:clinicalCurrentUser') ?? 'null');
    return typeof user?.id === 'string' ? user.id : 'local';
  } catch { return 'local'; }
}

function snapshotKey(patientId: string): string {
  return `${SNAPSHOT_PREFIX}${encodeURIComponent(userId())}:${encodeURIComponent(patientId)}`;
}

function collect(): Record<string, string> {
  return Object.fromEntries(PATIENT_SESSION_KEYS.flatMap((key) => {
    const value = localStorage.getItem(key);
    return value === null ? [] : [[key, value]];
  }));
}

function removeActiveValues(): void {
  PATIENT_SESSION_KEYS.forEach((key) => localStorage.removeItem(key));
}

function notify(): void {
  controller.abort();
  controller = new AbortController();
  generation += 1;
  listeners.forEach((listener) => listener());
  if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') window.dispatchEvent(new Event(PATIENT_SCOPE_CHANGED_EVENT));
}

/** Select before loading: old clinical data and requests disappear immediately. */
export function selectPatientScope(patientId: string | null, restore = true): void {
  const previous = localStorage.getItem(ACTIVE_PATIENT_KEY);
  const owner = localStorage.getItem(OWNER_KEY);
  // Pre-isolation global pointers carry no proven patient/account ownership.
  // Restore persisted server data instead of importing that ambiguous cache.
  const sameOwner = owner === userId();
  if (previous === patientId && sameOwner) return;
  if (previous && sameOwner) localStorage.setItem(snapshotKey(previous), JSON.stringify(collect()));
  removeActiveValues();
  localStorage.removeItem(ACTIVE_PATIENT_KEY);
  localStorage.setItem(OWNER_KEY, userId());
  if (patientId) {
    localStorage.setItem(ACTIVE_PATIENT_KEY, patientId);
    if (restore && sameOwner) {
      try {
        const snapshot = JSON.parse(localStorage.getItem(snapshotKey(patientId)) ?? '{}');
        for (const key of PATIENT_SESSION_KEYS) {
          if (typeof snapshot?.[key] === 'string') localStorage.setItem(key, snapshot[key]);
        }
      } catch { /* A damaged cache cannot supply clinical context. */ }
    }
  }
  notify();
}

export function clearPatientScope(): void {
  // New, unsaved workflows must also invalidate their in-flight requests.
  if (localStorage.getItem(ACTIVE_PATIENT_KEY)) selectPatientScope(null, false);
  else { removeActiveValues(); notify(); }
}

export function forgetPatientScope(patientId: string): void {
  if (localStorage.getItem(ACTIVE_PATIENT_KEY) === patientId) clearPatientScope();
  localStorage.removeItem(snapshotKey(patientId));
}

export type PatientScope = { patientId: string | null; generation: number; owner: string; signal: AbortSignal };
export function capturePatientScope(): PatientScope {
  return { patientId: localStorage.getItem(ACTIVE_PATIENT_KEY), generation, owner: userId(), signal: controller.signal };
}
export function isCurrentPatientScope(scope: PatientScope): boolean {
  return scope.generation === generation && scope.owner === userId()
    && scope.patientId === localStorage.getItem(ACTIVE_PATIENT_KEY) && !scope.signal.aborted;
}
export function assertCurrentPatientScope(scope: PatientScope): void {
  if (!isCurrentPatientScope(scope)) throw new DOMException('Hasta değişti; önceki işlemin sonucu uygulanmadı.', 'AbortError');
}
export function bindPatientMetadata(metadata: Record<string, unknown> | undefined, patientId: string | null): Record<string, unknown> {
  const sourcePatientId = metadata?.patient_id;
  if (typeof sourcePatientId === 'string' && sourcePatientId && sourcePatientId !== patientId) {
    throw new Error('Belge verisi seçilen hasta ile eşleşmiyor.');
  }
  return { ...metadata, ...(patientId ? { patient_id: patientId } : {}) };
}
export function subscribePatientScope(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function patientScopeVersion(): number { return generation; }
