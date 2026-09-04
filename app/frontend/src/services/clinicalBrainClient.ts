import { apiClient } from './apiClient';
import type { ClinicalIntakeInput, LabAnalysisResult } from './labAnalysisClient';
import type { RadiologyReport } from './radiologyClient';

export type ClinicalBrainSourceSummaries = {
  clinical: string;
  laboratory: string;
  ultrasound: string;
};

export type ClinicalBrainSourceAvailability = {
  clinical: boolean;
  laboratory: boolean;
  ultrasound: boolean;
};

export type ClinicalBrainSourceDates = {
  laboratory: string | null;
  ultrasound: string | null;
};

export type ClinicalBrainPerformedStudy = {
  canonical_code: string;
  name: string;
  date: string | null;
  source_report_id: string;
};

export type DoctorSignalSeverity = 'low' | 'moderate' | 'high';

export type DoctorInterpretationItem = {
  id: string;
  title: string;
  system: string;
  severity: DoctorSignalSeverity;
  markers: string[];
  interpretation: string;
  clinical_context: string;
  suggested_doctor_action: string;
};

export type DoctorInterpretationSummary = {
  abnormal_count: number;
  low_count: number;
  high_count: number;
  items: DoctorInterpretationItem[];
  safety_note: string;
};

export type CompatibilityLevel =
  | 'very_low'
  | 'low'
  | 'moderate'
  | 'high'
  | 'very_high';

export type CompatibilityDomain =
  | 'clinical_findings'
  | 'laboratory_findings'
  | 'imaging_findings'
  | 'cross_modal_consistency';

export type CompatibilityEvidence = {
  code: string;
  label: string;
  domain: CompatibilityDomain;
  points: number;
  maximum_points: number;
  matched: boolean;
  detail: string;
};

export type ClinicalCompatibilityScore = {
  hypothesis_code: 'acute_calculous_cholecystitis';
  display_name: 'Akut kalkülöz kolesistit';
  score: number;
  maximum_score: 100;
  level: CompatibilityLevel;
  level_label: string;
  score_type: 'rule_based_evidence_compatibility';
  estimated_probability: null;
  data_completeness_percent: number;
  breakdown: Array<{
    domain: CompatibilityDomain;
    label: string;
    score: number;
    maximum_score: number;
  }>;
  evidence: CompatibilityEvidence[];
  supporting_evidence: CompatibilityEvidence[];
  missing_data: string[];
  requires_clinician_review: true;
  disclaimer: string;
};

export type ClinicalBrainResult = {
  contract_version: 'clinical-brain-v1';
  source_summaries: ClinicalBrainSourceSummaries;
  ai_source_summaries: ClinicalBrainSourceSummaries;
  source_availability: ClinicalBrainSourceAvailability;
  source_dates: ClinicalBrainSourceDates;
  temporal_gap_days: number | null;
  performed_studies: ClinicalBrainPerformedStudy[];
  ultrasound_context_flags: string[];
  selected_ultrasound_report_id: string | null;
  doctor_interpretation: DoctorInterpretationSummary;
  compatibility: ClinicalCompatibilityScore;
  requires_physician_review: true;
  disclaimer: string;
};

export type ClinicalBrainInput = {
  clinical_context: ClinicalIntakeInput | null;
  lab_results: LabAnalysisResult[];
  radiology_reports: RadiologyReport[];
  language?: string;
};

/**
 * Thin browser adapter. Clinical decisions and summaries are intentionally owned by
 * the Python backend; this function only transports structured inputs/outputs.
 */
export async function evaluateClinicalBrain(
  input: ClinicalBrainInput,
): Promise<ClinicalBrainResult> {
  return apiClient.post<ClinicalBrainResult>('/clinical-brain/evaluate', input);
}
