const MASK_ENV = import.meta.env.VITE_MASK_PATIENT_IDENTIFIERS;
const DEMO_ENV = import.meta.env.VITE_DEMO_MODE;

/**
 * Development/demo privacy guard.
 *
 * - VITE_MASK_PATIENT_IDENTIFIERS=true  -> always mask
 * - VITE_MASK_PATIENT_IDENTIFIERS=false -> explicitly disable mask
 * - otherwise Vite development and explicit demo mode are masked by default
 */
export function shouldMaskPatientIdentifiers() {
  if (MASK_ENV === 'true') return true;
  if (MASK_ENV === 'false') return false;
  return import.meta.env.DEV || DEMO_ENV === 'true';
}

export function maskPatientName(value: string | null | undefined) {
  const name = value?.trim();
  if (!name) return value ?? '';
  return shouldMaskPatientIdentifiers() ? 'Demo Hasta' : name;
}

export function maskIdentifier(value: string | null | undefined) {
  const identifier = value?.trim();
  if (!identifier) return value ?? '';
  if (!shouldMaskPatientIdentifiers()) return identifier;

  const visibleTail = identifier.replace(/\D/g, '').slice(-2);
  return visibleTail ? `•••••••••${visibleTail}` : '•••••••••••';
}

export function privacyModeLabel() {
  return shouldMaskPatientIdentifiers()
    ? 'Geliştirme/demo gizlilik maskesi etkin'
    : null;
}
