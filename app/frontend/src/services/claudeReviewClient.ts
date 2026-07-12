import { getAccessToken } from './authClient';
import type { ClinicalHypothesis } from './clinicalHypothesesClient';
import type { ClinicalIntakeInput } from './labAnalysisClient';
import {
  listPatientRadiologyReports,
  type RadiologyReport,
} from './radiologyClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

const ACTIVE_CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';

export type ClaudeClinicalContext = ClinicalIntakeInput;

export type ClaudeSuggestedTest = {
  name: string;
  rationale: string | null;
  priority: 'routine' | 'soon' | 'urgent' | null;
};

export type ClaudeEvaluationMetadata = Record<string, unknown> & {
  possible_conditions?: string[];
  recommended_laboratory_tests?: ClaudeSuggestedTest[];
  recommended_imaging_tests?: ClaudeSuggestedTest[];
  limitations?: string[];
  requires_physician_review?: boolean;
};

export type ClaudeEvaluationHypothesis = ClinicalHypothesis & {
  metadata_json: ClaudeEvaluationMetadata;
};

export type ClaudeReviewGenerationResult = {
  analysis_run_id: string;
  lab_report_id: string | null;
  patient_id: string | null;
  created_hypotheses: ClaudeEvaluationHypothesis[];
  drafts_count: number;
  created_count: number;
  warnings: string[];
  hypotheses?: ClaudeEvaluationHypothesis[];
  generated_count?: number;
};

function authHeaders(): HeadersInit {
  const token = getAccessToken();

  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function readErrorMessage(response: Response): Promise<string> {
  const contentType = response.headers.get('content-type') ?? '';

  if (contentType.includes('application/json')) {
    try {
      const body = await response.json();

      if (typeof body?.detail === 'string') {
        return body.detail;
      }

      return JSON.stringify(body);
    } catch {
      return response.statusText;
    }
  }

  return response.text();
}

function readStoredClinicalContext(): ClaudeClinicalContext | undefined {
  try {
    const raw = localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY);
    if (!raw) return undefined;
    return JSON.parse(raw) as ClaudeClinicalContext;
  } catch {
    return undefined;
  }
}

function compactReport(report: RadiologyReport) {
  const measurements = report.measurements
    .slice(0, 20)
    .map((item) => `${item.value} ${item.unit}: ${item.context}`)
    .join('\n');
  const dexaMetrics = report.dexa_metrics
    .slice(0, 20)
    .map(
      (item) =>
        `${item.site}: BMD ${item.bmd ?? '-'} ${item.bmd_unit ?? ''}, T-score ${
          item.t_score ?? '-'
        }, Z-score ${item.z_score ?? '-'}`,
    )
    .join('\n');

  return [
    `Tarih: ${report.report_date ?? 'belirtilmedi'}`,
    `Modalite: ${report.modality}`,
    `Bölge: ${report.body_part}`,
    report.impression ? `Sonuç/izlenim: ${report.impression}` : null,
    report.critical_findings.length
      ? `Kritik ifadeler: ${report.critical_findings.join(', ')}`
      : null,
    measurements ? `Ölçümler:\n${measurements}` : null,
    dexaMetrics ? `DEXA ölçümleri:\n${dexaMetrics}` : null,
    `Orijinal rapor metni:\n${report.original_text.slice(0, 12000)}`,
  ]
    .filter(Boolean)
    .join('\n');
}

function mergeRadiologyIntoContext(
  context: ClaudeClinicalContext,
  reports: RadiologyReport[],
): ClaudeClinicalContext {
  const grouped: Record<keyof ClaudeClinicalContext['imaging_results'], string[]> = {
    xray: [],
    ultrasound: [],
    ct: [],
    mri: [],
    pet_ct: [],
    pathology: [],
  };

  for (const report of reports.slice(0, 20)) {
    const text = compactReport(report);
    switch (report.modality) {
      case 'XRAY':
        grouped.xray.push(text);
        break;
      case 'ULTRASOUND':
        grouped.ultrasound.push(text);
        break;
      case 'CT':
        grouped.ct.push(text);
        break;
      case 'MRI':
        grouped.mri.push(text);
        break;
      case 'PET_CT':
        grouped.pet_ct.push(text);
        break;
      case 'DEXA':
        grouped.pathology.push(`DEXA RAPORU\n${text}`);
        break;
      default:
        grouped.pathology.push(`DİĞER GÖRÜNTÜLEME RAPORU\n${text}`);
    }
  }

  const existing = context.imaging_results;
  const combine = (current: string | null, values: string[]) =>
    [current, ...values].filter(Boolean).join('\n\n---\n\n') || null;

  return {
    ...context,
    imaging_results: {
      xray: combine(existing.xray, grouped.xray),
      ultrasound: combine(existing.ultrasound, grouped.ultrasound),
      ct: combine(existing.ct, grouped.ct),
      mri: combine(existing.mri, grouped.mri),
      pet_ct: combine(existing.pet_ct, grouped.pet_ct),
      pathology: combine(existing.pathology, grouped.pathology),
    },
  };
}

async function buildUnifiedClinicalContext(
  suppliedContext?: ClaudeClinicalContext,
): Promise<{ context: ClaudeClinicalContext | undefined; radiologyCount: number }> {
  const baseContext = readStoredClinicalContext() ?? suppliedContext;
  if (!baseContext) return { context: undefined, radiologyCount: 0 };

  try {
    const reports = await listPatientRadiologyReports();
    return {
      context: mergeRadiologyIntoContext(baseContext, reports),
      radiologyCount: reports.length,
    };
  } catch {
    return { context: baseContext, radiologyCount: 0 };
  }
}

function compactClinicalContext(
  clinicalContext: ClaudeClinicalContext | undefined,
): string | null {
  if (!clinicalContext) return null;

  try {
    return JSON.stringify(clinicalContext);
  } catch {
    return null;
  }
}

export async function evaluateClaudeAbnormalResults(
  analysisRunId: string,
  maxHypotheses: number,
  clinicalContext?: ClaudeClinicalContext,
): Promise<ClaudeReviewGenerationResult> {
  const unified = await buildUnifiedClinicalContext(clinicalContext);
  const context = unified.context;

  const response = await fetch(
    `${API_BASE_URL}/analysis-runs/${analysisRunId}/clinical-hypotheses/generate`,
    {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        max_hypotheses: Math.max(1, Math.min(maxHypotheses, 10)),
        include_normal_results: false,
        include_needs_review_only: false,
        min_confidence: null,
        language: 'tr',
        metadata_json: {
          source: 'unified_patient_clinical_evaluation',
          normal_results_excluded: true,
          chief_complaint:
            context?.presenting_complaint.chief_complaint ?? null,
          clinical_history: compactClinicalContext(context),
          clinical_context: context ?? null,
          included_data_sources: {
            patient_information: Boolean(context?.patient_information),
            complaint_and_symptoms: Boolean(context?.presenting_complaint),
            medical_history: Boolean(context?.clinical_history_details),
            physical_exam_and_vitals: Boolean(context?.physical_exam),
            laboratory_results: true,
            radiology_and_dexa_reports: unified.radiologyCount,
          },
          requested_output: {
            possible_conditions: true,
            recommended_laboratory_tests: true,
            recommended_imaging_tests: true,
          },
        },
      }),
    },
  );

  if (!response.ok) {
    const detail = await readErrorMessage(response);
    throw new Error(`Claude değerlendirmesi başarısız: ${response.status} ${detail}`);
  }

  return response.json();
}

/** Backward-compatible alias for older callers. */
export const generateClaudeAbnormalReview = evaluateClaudeAbnormalResults;
