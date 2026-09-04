import {
  evaluateClinicalBrain,
  type ClinicalCompatibilityScore,
  type CompatibilityDomain,
  type CompatibilityEvidence,
  type CompatibilityLevel,
} from './clinicalBrainClient';
import type { ClinicalIntakeInput, LabAnalysisResult } from './labAnalysisClient';
import type { RadiologyReport } from './radiologyClient';

export type {
  ClinicalCompatibilityScore,
  CompatibilityDomain,
  CompatibilityEvidence,
  CompatibilityLevel,
};

export type CompatibilityBreakdown = ClinicalCompatibilityScore['breakdown'][number];

type ScoreInput = {
  clinicalContext: ClinicalIntakeInput | null;
  labResults: LabAnalysisResult[];
  reports: RadiologyReport[];
};

/**
 * @deprecated The rule engine moved to Python. New code should call
 * `evaluateClinicalBrain()` once per case and read `.compatibility`.
 *
 * This compatibility shim performs a backend call; no disease-scoring rule remains
 * in the browser.
 */
export async function calculateAcuteCholecystitisCompatibility(
  input: ScoreInput,
): Promise<ClinicalCompatibilityScore> {
  const result = await evaluateClinicalBrain({
    clinical_context: input.clinicalContext,
    lab_results: input.labResults,
    radiology_reports: input.reports,
    language: 'tr',
  });
  return result.compatibility;
}
