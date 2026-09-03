import { apiClient } from './apiClient';

export type ClinicalFusionSourceType =
  | 'clinical'
  | 'history'
  | 'vital'
  | 'laboratory'
  | 'imaging'
  | 'ai_detector'
  | 'ai_reader'
  | 'other';

export type ClinicalFusionPolarity = 'support' | 'oppose' | 'uncertain';
export type ClinicalFusionSeverity = 'low' | 'moderate' | 'high' | 'critical';
export type ClinicalFusionLevel =
  | 'very_low'
  | 'low'
  | 'moderate'
  | 'high'
  | 'very_high';

export type ClinicalFusionCandidate = {
  code: string;
  display_name: string;
  category?: string | null;
};

export type ClinicalFusionEvidence = {
  id: string;
  finding_code: string;
  label: string;
  source_type: ClinicalFusionSourceType;
  source_name: string;
  dependency_group?: string | null;
  polarity: ClinicalFusionPolarity;
  strength?: number;
  confidence?: number;
  severity?: ClinicalFusionSeverity;
  hypothesis_codes?: string[];
  observed_at?: string | null;
  location?: Record<string, unknown> | null;
  value?: string | number | null;
  unit?: string | null;
  model_id?: string | null;
  metadata?: Record<string, unknown>;
};

export type ClinicalFusionInput = {
  candidates: ClinicalFusionCandidate[];
  evidence: ClinicalFusionEvidence[];
  source_availability?: Record<string, boolean>;
  language?: string;
};

export type ClinicalFusionCandidateResult = {
  code: string;
  display_name: string;
  category: string | null;
  compatibility_score: number;
  compatibility_level: ClinicalFusionLevel;
  level_label: string;
  score_type: 'deterministic_evidence_compatibility';
  estimated_probability: null;
  support_strength: number;
  oppose_strength: number;
  support_group_count: number;
  oppose_group_count: number;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  uncertain_evidence_ids: string[];
  supporting_source_types: string[];
  limitations: string[];
  summary: string;
  requires_physician_review: true;
};

export type ClinicalFusionDisagreement = {
  kind:
    | 'cross_source_conflict'
    | 'ai_model_disagreement'
    | 'ai_vs_primary_evidence';
  hypothesis_code: string;
  evidence_ids: string[];
  detail: string;
};

export type ClinicalFusionResult = {
  contract_version: 'clinical-fusion-v1';
  candidates: ClinicalFusionCandidateResult[];
  critical_signal_ids: string[];
  disagreements: ClinicalFusionDisagreement[];
  core_source_coverage: Record<'clinical' | 'laboratory' | 'imaging', boolean>;
  core_source_count: number;
  core_source_total: 3;
  data_completeness_percent: number;
  ai_reader_available: boolean;
  unmapped_hypothesis_codes: string[];
  warnings: string[];
  requires_physician_review: true;
  disclaimer: string;
};

export async function evaluateClinicalFusion(
  input: ClinicalFusionInput,
): Promise<ClinicalFusionResult> {
  return apiClient.post<ClinicalFusionResult>('/clinical-fusion/evaluate', input);
}
