import type { ClinicalContext, VitalSigns, SexValue } from './simpleCaseClient';
import type { ClinicalIntakeInput } from './labAnalysisClient';

export const VITAL_FIELDS: Array<{ key: keyof VitalSigns; label: string; unit: string; min: number; max: number; step: string }> = [
  { key: 'systolic_bp', label: 'Sistolik tansiyon', unit: 'mmHg', min: 0, max: 400, step: '1' },
  { key: 'diastolic_bp', label: 'Diyastolik tansiyon', unit: 'mmHg', min: 0, max: 300, step: '1' },
  { key: 'heart_rate', label: 'Nabız', unit: 'bpm', min: 0, max: 350, step: '1' },
  { key: 'temperature', label: 'Ateş', unit: '°C', min: 10, max: 50, step: '0.1' },
  { key: 'spo2', label: 'SpO₂', unit: '%', min: 0, max: 100, step: '0.1' },
  { key: 'respiratory_rate', label: 'Solunum sayısı', unit: '/dk', min: 0, max: 120, step: '1' },
  { key: 'height_cm', label: 'Boy', unit: 'cm', min: 10, max: 300, step: '0.1' },
  { key: 'weight_kg', label: 'Kilo', unit: 'kg', min: 0.1, max: 700, step: '0.1' },
  { key: 'glucose_mg_dl', label: 'Kan şekeri (isteğe bağlı)', unit: 'mg/dL', min: 0, max: 2000, step: '0.1' },
];
export type VitalDraft = Record<keyof VitalSigns, string>;
export function vitalDraft(vitals?: VitalSigns | null): VitalDraft {
  return Object.fromEntries(VITAL_FIELDS.map(({ key }) => [key, vitals?.[key] == null ? '' : String(vitals[key])])) as VitalDraft;
}
export function parseVitalDraft(draft: VitalDraft): { values: VitalSigns; errors: string[] } {
  const errors: string[] = [];
  const values = Object.fromEntries(VITAL_FIELDS.map(({ key, label, min, max }) => {
    const text = draft[key].trim();
    if (!text) return [key, null];
    const value = Number(text.replace(',', '.'));
    if (!Number.isFinite(value) || value < min || value > max) {
      errors.push(`${label}: ${min}–${max} aralığında bir sayı girin.`);
      return [key, null];
    }
    return [key, value];
  })) as VitalSigns;
  return { values, errors };
}

type RecordLike = { clinical?: ClinicalContext; sex?: string; metadata_json?: Record<string, unknown> };
function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function lines(value: unknown): string[] {
  return (Array.isArray(value) ? value : [value]).flatMap((item) => typeof item === 'string' ? item.split(/\r?\n/).map((line) => line.trim()).filter(Boolean) : []);
}
function number(value: unknown): number | null {
  if (value === null || value === undefined || typeof value === 'boolean') return null;
  if (typeof value === 'string' && !value.trim()) return null;
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  const result = Number(String(value).replace(',', '.'));
  return Number.isFinite(result) ? result : null;
}

export function normalizeClinical(source: unknown, metadata: Record<string, unknown> = {}): ClinicalContext {
  const raw = object(source), patient = object(raw.patient_information);
  const complaint = object(raw.presenting_complaint), history = object(raw.clinical_history_details), exam = object(raw.physical_exam);
  const modern = ['complaints', 'history', 'medications', 'notes'].some((key) => key in raw);
  const legacyVitals = {
    systolic_bp: exam.blood_pressure_systolic, diastolic_bp: exam.blood_pressure_diastolic,
    heart_rate: exam.pulse_bpm, respiratory_rate: exam.respiratory_rate,
    temperature: exam.temperature_c, spo2: exam.oxygen_saturation_percent,
    height_cm: patient.height_cm ?? metadata.height_cm, weight_kg: patient.weight_kg ?? metadata.weight_kg,
  };
  const rawVitals = 'vital_signs' in raw ? object(raw.vital_signs) : legacyVitals;
  const vitals = Object.fromEntries(VITAL_FIELDS.map(({ key, min, max }) => {
    const value = number(object(rawVitals)[key]);
    return [key, value !== null && value >= min && value <= max ? value : null];
  })) as VitalSigns;
  const sex = raw.sex ?? patient.sex ?? metadata.sex;
  return {
    age: number(raw.age ?? patient.age ?? metadata.age),
    sex: (['male', 'female', 'other'].includes(String(sex)) ? sex : 'unknown') as SexValue,
    complaints: modern ? lines(raw.complaints) : ['chief_complaint', 'associated_symptoms', 'reason_for_visit', 'complaint_duration'].flatMap((key) => lines(complaint[key])),
    history: modern ? lines(raw.history) : ['history_of_present_illness', 'current_medical_conditions', 'past_medical_history', 'family_history', 'allergies', 'tobacco_alcohol', 'past_surgeries'].flatMap((key) => lines(history[key])),
    medications: lines(modern ? raw.medications : history.medications),
    notes: lines(modern ? raw.notes : exam.examination_findings).join('\n') || null,
    vital_signs: vitals,
  };
}
export function recordClinical(record: RecordLike): ClinicalContext {
  const metadata = record.metadata_json ?? {};
  const source = record.clinical ?? object(metadata.simple_case).clinical ?? metadata.clinical_context;
  return normalizeClinical(source, { ...metadata, sex: record.sex });
}
export function clinicalRows(clinical: ClinicalContext): Array<[string, string]> {
  return [
    ['Şikayetler', clinical.complaints.join('\n')], ['Özgeçmiş / Hastalıklar', clinical.history.join('\n')],
    ['İlaçlar', clinical.medications.join('\n')], ['Ek Klinik Not', clinical.notes ?? ''],
  ].filter((item): item is [string, string] => Boolean(item[1].trim()));
}
export function formatVitals(vitals?: VitalSigns | null): string[] {
  if (!vitals) return [];
  const parts: string[] = [];
  if (vitals.systolic_bp != null && vitals.diastolic_bp != null) parts.push(`TA ${vitals.systolic_bp}/${vitals.diastolic_bp} mmHg`);
  else if (vitals.systolic_bp != null) parts.push(`Sistolik TA ${vitals.systolic_bp} mmHg`);
  else if (vitals.diastolic_bp != null) parts.push(`Diyastolik TA ${vitals.diastolic_bp} mmHg`);
  for (const [key, label, unit] of [
    ['heart_rate', 'Nabız', '/dk'], ['temperature', 'Ateş', '°C'], ['spo2', 'SpO₂', '%'],
    ['respiratory_rate', 'Solunum', '/dk'], ['height_cm', 'Boy', ' cm'], ['weight_kg', 'Kilo', ' kg'], ['glucose_mg_dl', 'Kan şekeri', ' mg/dL'],
  ] as const) {
    if (vitals[key] != null) parts.push(key === 'spo2' ? `${label} %${vitals[key]}` : `${label} ${vitals[key]}${unit}`);
  }
  return parts;
}

export function legacyClinicalIntake(clinical: ClinicalContext, previous?: unknown): ClinicalIntakeInput {
  const original = object(previous);
  const patient = object(original.patient_information);
  const complaint = object(original.presenting_complaint);
  const history = object(original.clinical_history_details);
  const exam = object(original.physical_exam);
  const imaging = object(original.imaging_results);
  const vitals = clinical.vital_signs;
  const previousClinical = normalizeClinical(original);
  const sameComplaints = JSON.stringify(previousClinical.complaints) === JSON.stringify(clinical.complaints);
  const sameHistory = JSON.stringify(previousClinical.history) === JSON.stringify(clinical.history);
  // Keep the old form's separate fields only when they describe the canonical
  // content. A stale legacy context must not replace a newer case snapshot.
  const preservedComplaint = sameComplaints ? complaint : {};
  const preservedHistory = sameHistory ? history : {};
  return {
    patient_information: {
      full_name: typeof patient.full_name === 'string' ? patient.full_name : null,
      age: clinical.age, sex: clinical.sex,
      height_cm: vitals?.height_cm ?? null, weight_kg: vitals?.weight_kg ?? null,
    },
    presenting_complaint: {
      reason_for_visit: null, complaint_duration: null, severity_score: null, associated_symptoms: null,
      ...preservedComplaint,
      chief_complaint: sameComplaints && 'presenting_complaint' in original
        ? (complaint.chief_complaint as string | null ?? null)
        : clinical.complaints.join('\n') || null,
    },
    clinical_history_details: {
      history_of_present_illness: null, current_medical_conditions: null,
      family_history: null, allergies: null, tobacco_alcohol: null, past_surgeries: null,
      ...preservedHistory,
      past_medical_history: sameHistory && 'clinical_history_details' in original
        ? (history.past_medical_history as string | null ?? null)
        : clinical.history.join('\n') || null,
      medications: clinical.medications.join('\n') || null,
    },
    physical_exam: {
      ...exam,
      blood_pressure_systolic: vitals?.systolic_bp ?? null,
      blood_pressure_diastolic: vitals?.diastolic_bp ?? null,
      pulse_bpm: vitals?.heart_rate ?? null, temperature_c: vitals?.temperature ?? null,
      respiratory_rate: vitals?.respiratory_rate ?? null,
      oxygen_saturation_percent: vitals?.spo2 ?? null,
      examination_findings: clinical.notes,
    },
    imaging_results: { xray: null, ultrasound: null, ct: null, mri: null, pet_ct: null, pathology: null, ...imaging },
    attachments: Array.isArray(original.attachments) ? original.attachments as ClinicalIntakeInput['attachments'] : [],
    vital_signs: vitals,
  };
}
