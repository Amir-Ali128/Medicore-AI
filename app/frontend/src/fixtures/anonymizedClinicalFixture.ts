import type { ClinicalIntakeInput } from '../services/labAnalysisClient';

/**
 * Synthetic fixture for screenshots, demos and local development.
 * No field is copied from a real patient record.
 */
export const ANONYMIZED_CLINICAL_FIXTURE: ClinicalIntakeInput = {
  patient_information: {
    full_name: 'Demo Hasta',
    age: 48,
    sex: 'unknown',
    height_cm: null,
    weight_kg: null,
  },
  presenting_complaint: {
    reason_for_visit: 'Demo klinik değerlendirme',
    chief_complaint: 'karın ağrısı',
    complaint_duration: null,
    severity_score: null,
    associated_symptoms: null,
  },
  clinical_history_details: {
    history_of_present_illness: null,
    current_medical_conditions: null,
    past_medical_history: null,
    family_history: null,
    medications: null,
    allergies: null,
    tobacco_alcohol: null,
    past_surgeries: null,
  },
  physical_exam: {
    blood_pressure_systolic: null,
    blood_pressure_diastolic: null,
    pulse_bpm: null,
    temperature_c: null,
    respiratory_rate: null,
    oxygen_saturation_percent: null,
    examination_findings: null,
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

export function createAnonymizedClinicalFixture(): ClinicalIntakeInput {
  return structuredClone(ANONYMIZED_CLINICAL_FIXTURE);
}
