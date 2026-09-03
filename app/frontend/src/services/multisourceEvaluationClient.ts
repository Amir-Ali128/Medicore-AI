import { getAccessToken } from './authClient';
import type { ClaudeReviewGenerationResult } from './claudeReviewClient';
import type {
  CaseSourceDates,
  CaseSourceSummaries,
  PerformedStudy,
} from './caseEvaluationSummary';
import type { ClinicalIntakeInput } from './labAnalysisClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export type CaseSourceAvailability = {
  clinical: boolean;
  laboratory: boolean;
  ultrasound: boolean;
};

export type MultisourceQualityContext = {
  performedStudies: PerformedStudy[];
  sourceDates: CaseSourceDates;
  sourceAvailability: CaseSourceAvailability;
};

function cleanText(value: string | null | undefined) {
  const cleaned = value?.replace(/\s+/g, ' ').trim();
  return cleaned ? cleaned.slice(0, 240) : null;
}

function buildCompactSymptoms(context: ClinicalIntakeInput | null) {
  const complaint = context?.presenting_complaint;
  if (!complaint) return [];

  const chief = cleanText(complaint.chief_complaint);
  const duration = cleanText(complaint.complaint_duration);
  const values = [
    chief && duration ? `${chief} (${duration})`.slice(0, 240) : chief,
    cleanText(complaint.associated_symptoms),
    cleanText(complaint.reason_for_visit),
  ].filter((value): value is string => Boolean(value));

  return [...new Set(values)].slice(0, 4);
}

function buildCompactVitals(context: ClinicalIntakeInput | null) {
  const exam = context?.physical_exam;
  if (!exam) return {};

  return {
    blood_pressure_systolic: exam.blood_pressure_systolic ?? null,
    blood_pressure_diastolic: exam.blood_pressure_diastolic ?? null,
    pulse_bpm: exam.pulse_bpm ?? null,
    temperature_c: exam.temperature_c ?? null,
    respiratory_rate: exam.respiratory_rate ?? null,
    oxygen_saturation_percent: exam.oxygen_saturation_percent ?? null,
  };
}

function sourceCount(availability: CaseSourceAvailability) {
  return Object.values(availability).filter(Boolean).length;
}

function boundedSummary(
  summary: string,
  available: boolean,
) {
  return available ? summary.slice(0, 320) : '';
}

async function readErrorMessage(response: Response) {
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') return body.detail;
      return JSON.stringify(body);
    } catch {
      return response.statusText;
    }
  }
  return response.text();
}

export async function evaluateMultisourceCase(
  analysisRunId: string | null,
  patientId: string | null,
  clinicalContext: ClinicalIntakeInput | null,
  sourceSummaries: CaseSourceSummaries,
  contextFlags: string[],
  qualityContext: MultisourceQualityContext,
): Promise<ClaudeReviewGenerationResult> {
  const availableCount = sourceCount(qualityContext.sourceAvailability);
  if (availableCount === 0) {
    throw new Error('Değerlendirme için en az bir klinik kaynak gerekiyor.');
  }
  if (!analysisRunId && !patientId) {
    throw new Error(
      'Tek kaynaklı değerlendirme için önce hasta kaydını kaydetmelisin.',
    );
  }

  const token = getAccessToken();
  const endpoint = analysisRunId
    ? `${API_BASE_URL}/analysis-runs/${analysisRunId}/clinical-hypotheses/generate`
    : `${API_BASE_URL}/clinical-evaluations/source-only/generate`;

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      patient_id: patientId,
      max_hypotheses: 1,
      include_normal_results: false,
      include_needs_review_only: false,
      min_confidence: null,
      language: 'tr',
      metadata_json: {
        source:
          availableCount === 3
            ? 'compact_multisource_rule_gated_evaluation'
            : 'compact_partial_source_rule_gated_evaluation',
        normal_results_excluded: true,
        patient_age: clinicalContext?.patient_information.age ?? null,
        symptoms: buildCompactSymptoms(clinicalContext),
        vitals: buildCompactVitals(clinicalContext),
        source_summaries: {
          clinical: boundedSummary(
            sourceSummaries.clinical,
            qualityContext.sourceAvailability.clinical,
          ),
          laboratory: boundedSummary(
            sourceSummaries.laboratory,
            qualityContext.sourceAvailability.laboratory,
          ),
          ultrasound: boundedSummary(
            sourceSummaries.ultrasound,
            qualityContext.sourceAvailability.ultrasound,
          ),
        },
        source_availability: qualityContext.sourceAvailability,
        source_coverage: {
          available_count: availableCount,
          total_sources: 3,
          limited: availableCount < 3,
        },
        context_flags: contextFlags,
        performed_studies: qualityContext.performedStudies.slice(0, 24),
        source_dates: qualityContext.sourceDates,
      },
    }),
  });

  if (!response.ok) {
    const detail = await readErrorMessage(response);
    throw new Error(`AI değerlendirmesi başarısız: ${response.status} ${detail}`);
  }

  const result = (await response.json()) as ClaudeReviewGenerationResult;
  window.dispatchEvent(new Event('medicore:case-summary-updated'));
  return result;
}
