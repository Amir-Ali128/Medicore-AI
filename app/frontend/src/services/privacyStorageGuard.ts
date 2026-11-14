import {
  maskIdentifier,
  maskPatientName,
  shouldMaskPatientIdentifiers,
} from './privacyMode';

const PATIENT_NAME_KEY = 'medicore:lastPatientDisplayName';
const PATIENT_BIRTH_DATE_KEY = 'medicore:lastPatientBirthDate';
const CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';
const IDENTIFIER_KEY = /(?:tckn|tc[_-]?kimlik|national[_-]?id|identity[_-]?number)/i;
const DIRECT_IDENTIFIER_FIELD =
  /^(?:full_name|patient_name|display_name|first_name|last_name|surname|tckn|tc[_-]?kimlik\w*|national[_-]?id\w*|identity[_-]?number|phone|telephone|mobile|email|address|date_of_birth|birth_date|dob)$/i;

/**
 * Direct identifiers must never be written to persistent browser storage
 * (localStorage survives logout and is readable on shared clinic machines).
 * These keys are kept only for the lifetime of the tab (sessionStorage).
 */
const SESSION_ONLY_KEYS = new Set([PATIENT_NAME_KEY, PATIENT_BIRTH_DATE_KEY]);

export function stripDirectIdentifiers(value: string) {
  try {
    const parsed = JSON.parse(value) as Record<string, unknown>;
    const patient = parsed.patient_information;
    if (typeof patient !== 'object' || patient === null) return value;

    const patientRecord = patient as Record<string, unknown>;
    for (const [key, item] of Object.entries(patientRecord)) {
      if (typeof item !== 'string') continue;
      if (DIRECT_IDENTIFIER_FIELD.test(key) || IDENTIFIER_KEY.test(key)) {
        patientRecord[key] = null;
      }
    }

    return JSON.stringify(parsed);
  } catch {
    return value;
  }
}

function maskForDisplay(key: string, value: string) {
  if (!shouldMaskPatientIdentifiers()) return value;
  if (key === PATIENT_NAME_KEY) return maskPatientName(value);
  if (IDENTIFIER_KEY.test(key)) return maskIdentifier(value);
  return value;
}

function sanitizeLocalValue(key: string, value: string) {
  if (key === CLINICAL_INTAKE_KEY) return stripDirectIdentifiers(value);
  if (IDENTIFIER_KEY.test(key)) return maskIdentifier(value);
  return value;
}

function sessionStore(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/**
 * Always installed: keeps patient identifiers out of persistent localStorage.
 * In development/demo mode the session copies are additionally masked.
 * Backend payloads are untouched; the backend privacy gateway handles AI sends.
 */
export function installPrivacyStorageGuard() {
  if (typeof window === 'undefined' || typeof Storage === 'undefined') return;

  const prototype = Storage.prototype;

  // StrictMode/HMR can evaluate the entry point more than once.
  if ((prototype as Storage & { __medicorePrivacyGuard?: boolean }).__medicorePrivacyGuard) {
    return;
  }

  const currentSetItem = prototype.setItem;
  const currentGetItem = prototype.getItem;
  const currentRemoveItem = prototype.removeItem;

  Object.defineProperty(prototype, '__medicorePrivacyGuard', {
    value: true,
    configurable: true,
  });

  prototype.setItem = function setItemWithPrivacyGuard(
    this: Storage,
    key: string,
    value: string,
  ) {
    if (this === window.localStorage && SESSION_ONLY_KEYS.has(key)) {
      const session = sessionStore();
      if (session) currentSetItem.call(session, key, maskForDisplay(key, value));
      currentRemoveItem.call(this, key);
      return;
    }
    const nextValue =
      this === window.localStorage ? sanitizeLocalValue(key, value) : value;
    currentSetItem.call(this, key, nextValue);
  };

  prototype.getItem = function getItemWithPrivacyGuard(this: Storage, key: string) {
    if (this === window.localStorage && SESSION_ONLY_KEYS.has(key)) {
      const session = sessionStore();
      return session ? currentGetItem.call(session, key) : null;
    }
    return currentGetItem.call(this, key);
  };

  prototype.removeItem = function removeItemWithPrivacyGuard(this: Storage, key: string) {
    if (this === window.localStorage && SESSION_ONLY_KEYS.has(key)) {
      const session = sessionStore();
      if (session) currentRemoveItem.call(session, key);
    }
    currentRemoveItem.call(this, key);
  };

  // Purge identifiers that were persisted before the guard existed.
  const keys: string[] = [];
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index);
    if (key) keys.push(key);
  }
  for (const key of keys) {
    const value = currentGetItem.call(window.localStorage, key);
    if (value == null) continue;
    if (SESSION_ONLY_KEYS.has(key)) {
      currentRemoveItem.call(window.localStorage, key);
      continue;
    }
    const sanitized = sanitizeLocalValue(key, value);
    if (sanitized !== value) {
      currentSetItem.call(window.localStorage, key, sanitized);
    }
  }
}
