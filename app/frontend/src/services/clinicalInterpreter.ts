import {
  evaluateClinicalBrain,
  type DoctorInterpretationSummary as BackendDoctorInterpretationSummary,
  type DoctorSignalSeverity,
} from './clinicalBrainClient';
import type { LabAnalysisResult } from './labAnalysisClient';

export type { DoctorSignalSeverity };

export type DoctorInterpretationItem = {
  id: string;
  title: string;
  system: string;
  severity: DoctorSignalSeverity;
  markers: string[];
  interpretation: string;
  clinicalContext: string;
  suggestedDoctorAction: string;
};

export type DoctorInterpretationSummary = {
  abnormalCount: number;
  lowCount: number;
  highCount: number;
  items: DoctorInterpretationItem[];
  safetyNote: string;
};

function toLegacyPresentationShape(
  summary: BackendDoctorInterpretationSummary,
): DoctorInterpretationSummary {
  return {
    abnormalCount: summary.abnormal_count,
    lowCount: summary.low_count,
    highCount: summary.high_count,
    items: summary.items.map((item) => ({
      id: item.id,
      title: item.title,
      system: item.system,
      severity: item.severity,
      markers: item.markers,
      interpretation: item.interpretation,
      clinicalContext: item.clinical_context,
      suggestedDoctorAction: item.suggested_doctor_action,
    })),
    safetyNote: summary.safety_note,
  };
}

/**
 * @deprecated Lab interpretation now lives in Python Clinical Brain. New screens
 * should call `evaluateClinicalBrain()` once and render `.doctor_interpretation`.
 * This shim keeps the old presentation shape but performs no local clinical rules.
 */
export async function buildDoctorInterpretation(
  results: LabAnalysisResult[],
): Promise<DoctorInterpretationSummary> {
  const brain = await evaluateClinicalBrain({
    clinical_context: null,
    lab_results: results,
    radiology_reports: [],
    language: 'tr',
  });
  return toLegacyPresentationShape(brain.doctor_interpretation);
}
