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

export type ClinicalCaseSignalKind = 'symptom' | 'exam' | 'history' | 'vital';
export type ImagingCaseSignalKind = 'primary' | 'detector';

type CaseSignalBase = {
  id: string;
  finding_code: string;
  label: string;
  polarity?: ClinicalFusionPolarity;
  hypothesis_codes?: string[];
  strength?: number;
  confidence?: number;
  severity?: ClinicalFusionSeverity;
  observed_at?: string | null;
  value?: string | number | null;
  unit?: string | null;
  location?: Record<string, unknown> | null;
  metadata?: Record<string, unknown>;
};

export type ClinicalCaseSignal = CaseSignalBase & {
  kind: ClinicalCaseSignalKind;
  source_name?: string;
};

export type LaboratoryCaseSignal = CaseSignalBase & {
  report_id?: string | null;
  source_name?: string;
};

export type ImagingCaseSignal = CaseSignalBase & {
  study_id: string;
  kind?: ImagingCaseSignalKind;
  source_name?: string;
  model_id?: string | null;
};

export type AIReaderCaseSignal = CaseSignalBase & {
  study_id: string;
  provider: string;
  model_id?: string | null;
};

export type OnnxFindingScore = {
  label: string;
  score: number;
  threshold: number;
  above_threshold: boolean;
};

export type OnnxCaseRun = {
  run_id: string;
  study_id: string;
  model_id: string;
  model_version?: string | null;
  findings?: OnnxFindingScore[];
  hypothesis_map?: Record<string, string[]>;
  location_by_label?: Record<string, Record<string, unknown>>;
  severity_by_label?: Record<string, ClinicalFusionSeverity>;
  metadata?: Record<string, unknown>;
};

export type ClinicalFusionCaseInput = {
  case_id: string;
  candidates: ClinicalFusionCandidate[];
  clinical_signals?: ClinicalCaseSignal[];
  laboratory_signals?: LaboratoryCaseSignal[];
  imaging_signals?: ImagingCaseSignal[];
  ai_reader_signals?: AIReaderCaseSignal[];
  onnx_runs?: OnnxCaseRun[];
  source_availability?: Record<string, boolean>;
  language?: string;
};

export type ClinicalFusionGraphNode = {
  id: string;
  kind: 'candidate' | 'evidence' | 'dependency_group';
  label: string;
  source_type?: string | null;
  polarity?: ClinicalFusionPolarity | null;
};

export type ClinicalFusionGraphEdge = {
  source: string;
  target: string;
  relation: 'supports' | 'opposes' | 'uncertain_for' | 'member_of';
};

export type ClinicalFusionCaseResult = {
  contract_version: 'clinical-fusion-case-v1';
  fusion: ClinicalFusionResult;
  normalized_evidence: ClinicalFusionEvidence[];
  graph_nodes: ClinicalFusionGraphNode[];
  graph_edges: ClinicalFusionGraphEdge[];
  source_evidence_counts: Record<string, number>;
  review_priority: 'routine' | 'priority' | 'critical';
  needs_conflict_review: boolean;
  adapter_warnings: string[];
  requires_physician_review: true;
};

export async function evaluateClinicalFusion(
  input: ClinicalFusionInput,
): Promise<ClinicalFusionResult> {
  return apiClient.post<ClinicalFusionResult>('/clinical-fusion/evaluate', input);
}

export async function evaluateClinicalFusionCase(
  input: ClinicalFusionCaseInput,
): Promise<ClinicalFusionCaseResult> {
  return apiClient.post<ClinicalFusionCaseResult>(
    '/clinical-fusion/evaluate-case',
    input,
  );
}
