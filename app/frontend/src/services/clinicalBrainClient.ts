import { apiClient } from './apiClient';
import type { ClinicalIntakeInput, LabAnalysisResult } from './labAnalysisClient';
import {
  isAnalyzableRadiologyReport,
  type RadiologyReport,
} from './radiologyClient';

export type ClinicalBrainSourceSummaries = {
  clinical: string;
  laboratory: string;
  ultrasound: string;
  /**
   * Generic imaging summary used only by the compact physician-review workflow.
   * The Python Clinical Brain still owns ultrasound-specific reasoning separately.
   */
  radiology?: string;
};

export type ClinicalBrainSourceAvailability = {
  clinical: boolean;
  laboratory: boolean;
  ultrasound: boolean;
  /** Generic analyzable radiology/imaging source for compact evaluation. */
  radiology?: boolean;
};

export type ClinicalBrainSourceDates = {
  laboratory: string | null;
  ultrasound: string | null;
  radiology?: string | null;
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

function compactRadiologySummary(report: RadiologyReport): string | null {
  const summary = report.summary?.replace(/\s+/g, ' ').trim();
  const impression = report.impression?.replace(/\s+/g, ' ').trim();
  const meaningfulSummary =
    summary && summary !== 'Rapor özeti oluşturulamadı.' ? summary : impression;
  if (!meaningfulSummary) return null;

  const modality = report.modality && report.modality !== 'UNKNOWN' ? report.modality : '';
  const bodyPart = report.body_part && report.body_part !== 'OTHER' ? report.body_part : '';
  const label = [modality, bodyPart].filter(Boolean).join(' / ');
  const text = label ? `${label}: ${meaningfulSummary}` : meaningfulSummary;
  return text.slice(0, 320);
}

function reportTimestamp(report: RadiologyReport): number {
  return (
    Date.parse(report.updated_at || report.created_at || report.report_date || '') || 0
  );
}

/**
 * Thin browser adapter. Clinical decisions and disease-specific imaging reasoning are
 * intentionally owned by the Python backend. This adapter only adds a generic,
 * bounded radiology source for the separate compact physician-review workflow.
 */
export async function evaluateClinicalBrain(
  input: ClinicalBrainInput,
): Promise<ClinicalBrainResult> {
  const result = await apiClient.post<ClinicalBrainResult>(
    '/clinical-brain/evaluate',
    input,
  );

  const latestRadiology = [...input.radiology_reports]
    .filter(isAnalyzableRadiologyReport)
    .sort((left, right) => reportTimestamp(right) - reportTimestamp(left))
    .find((report) => compactRadiologySummary(report) !== null) ?? null;
  const radiologySummary = latestRadiology
    ? compactRadiologySummary(latestRadiology)
    : null;
  const radiologyReady = Boolean(radiologySummary);

  // The UI historically reads `.ultrasound`, while its 3-source coverage counter
  // uses Object.values(). Keep ultrasound available for its specific rules without
  // counting it as a fourth source; radiology is the single imaging source group.
  const sourceAvailability: ClinicalBrainSourceAvailability = {
    clinical: result.source_availability.clinical,
    laboratory: result.source_availability.laboratory,
    radiology: radiologyReady,
    ultrasound: result.source_availability.ultrasound,
  };
  Object.defineProperty(sourceAvailability, 'ultrasound', {
    value: result.source_availability.ultrasound,
    enumerable: false,
    writable: false,
    configurable: false,
  });

  return {
    ...result,
    source_summaries: {
      ...result.source_summaries,
      radiology: radiologySummary ?? 'Radyoloji / görüntüleme özeti bulunamadı.',
    },
    ai_source_summaries: {
      ...result.ai_source_summaries,
      radiology: radiologySummary ?? '',
    },
    source_availability: sourceAvailability,
    source_dates: {
      ...result.source_dates,
      radiology:
        latestRadiology?.report_date ?? latestRadiology?.created_at?.slice(0, 10) ?? null,
    },
  };
}
