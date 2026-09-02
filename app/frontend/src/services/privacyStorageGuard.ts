import {
  maskIdentifier,
  maskPatientName,
  shouldMaskPatientIdentifiers,
} from './privacyMode';

const PATIENT_NAME_KEY = 'medicore:lastPatientDisplayName';
const CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';
const IDENTIFIER_KEY = /(?:tckn|tc[_-]?kimlik|national[_-]?id|identity[_-]?number)/i;

function sanitizeClinicalIntake(value: string) {
  try {
    const parsed = JSON.parse(value) as Record<string, unknown>;
    const patient = parsed.patient_information;
    if (typeof patient !== 'object' || patient === null) return value;

    const patientRecord = patient as Record<string, unknown>;
    if (typeof patientRecord.full_name === 'string') {
      patientRecord.full_name = maskPatientName(patientRecord.full_name);
    }

    for (const [key, item] of Object.entries(patientRecord)) {
      if (IDENTIFIER_KEY.test(key) && typeof item === 'string') {
        patientRecord[key] = maskIdentifier(item);
      }
    }

    return JSON.stringify(parsed);
  } catch {
    return value;
  }
}

function sanitizeStorageValue(key: string, value: string) {
  if (key === PATIENT_NAME_KEY) return maskPatientName(value);
  if (key === CLINICAL_INTAKE_KEY) return sanitizeClinicalIntake(value);
  if (IDENTIFIER_KEY.test(key)) return maskIdentifier(value);
  return value;
}

/**
 * Prevents accidental patient-identifier leakage in local development/demo UI.
 * Backend payloads are deliberately untouched so a controlled real-data test can
 * still exercise server behavior; only browser persistence/display state is masked.
 */
export function installPrivacyStorageGuard() {
  if (!shouldMaskPatientIdentifiers() || typeof window === 'undefined') return;

  const prototype = Storage.prototype;
  const currentSetItem = prototype.setItem;

  // StrictMode/HMR can evaluate the entry point more than once.
  if ((prototype as Storage & { __medicorePrivacyGuard?: boolean }).__medicorePrivacyGuard) {
    return;
  }

  Object.defineProperty(prototype, '__medicorePrivacyGuard', {
    value: true,
    configurable: true,
  });

  prototype.setItem = function setItemWithPrivacyGuard(key: string, value: string) {
    const nextValue =
      this === window.localStorage ? sanitizeStorageValue(key, value) : value;
    currentSetItem.call(this, key, nextValue);
  };

  // Sanitize identifiers that were persisted before the guard was installed.
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index);
    if (!key) continue;
    const value = window.localStorage.getItem(key);
    if (value == null) continue;
    const sanitized = sanitizeStorageValue(key, value);
    if (sanitized !== value) {
      currentSetItem.call(window.localStorage, key, sanitized);
    }
  }
}
