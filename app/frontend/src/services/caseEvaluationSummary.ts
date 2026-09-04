import type {
  ClinicalBrainPerformedStudy,
  ClinicalBrainSourceDates,
  ClinicalBrainSourceSummaries,
} from './clinicalBrainClient';

/**
 * @deprecated Clinical summary/source-selection logic now lives in
 * `POST /clinical-brain/evaluate`. This file intentionally contains no clinical
 * decision logic and remains only as a temporary type-compatibility surface.
 */
export type CaseSourceSummaries = ClinicalBrainSourceSummaries;
export type PerformedStudy = ClinicalBrainPerformedStudy;
export type CaseSourceDates = ClinicalBrainSourceDates;
