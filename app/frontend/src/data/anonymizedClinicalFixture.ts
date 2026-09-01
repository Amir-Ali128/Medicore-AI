import type { ClinicalIntakeInput } from '../services/labAnalysisClient';

/**
 * Synthetic-only fixture for development/demo screenshots and manual smoke tests.
 * It must never be replaced with copied patient identifiers.
 */
export const ANONYMIZED_CLINICAL_FIXTURE: ClinicalIntakeInput = {
  patient_information: {
    full_name: 'Demo Hasta',
    age: 52,
    sex: 'unknown',
    height_cm: null,
    weight_kg: null,
  },
  presenting_complaint: {
    reason_for_visit: 'Demo klinik değerlendirme',
    chief_complaint: 'Sentetik örnek yakınma',
    complaint_duration: '3 gün',
    severity_score: null,
    associated_symptoms: null,
  },
  clinical_history_details: {
    history_of_present_illness: 'Yalnızca geliştirme için sentetik klinik öykü.',
    current_medical_conditions: null,
    past_medical_history: null,
    family_history: null,
    medications: null,
    allergies: null,
    tobacco_alcohol: null,
    past_surgeries: null,
  },
  physical_exam: {
    blood_pressure_systolic: 120,
    blood_pressure_diastolic: 80,
    pulse_bpm: 72,
    temperature_c: 36.7,
    respiratory_rate: 16,
    oxygen_saturation_percent: 98,
    examination_findings: 'Sentetik demo muayene bulgusu.',
  },
  imaging_results: {
    xray: null,
    ultrasound: null,
    ct: null,
    mri: null,
    pet_ct: null,
    pathology: null,
  },
  attachments: [],
};

export const ANONYMIZED_DEMO_IDENTIFIERS = {
  protocol_no: 'DEMO-0001',
  external_ref: null,
  national_identifier: '***********',
} as const;
