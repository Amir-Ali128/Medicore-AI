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

export type MultisourceQualityContext = {
  performedStudies: PerformedStudy[];
  sourceDates: CaseSourceDates;
};

function cleanText(value: string | null | undefined) {
  const cleaned = value?.replace(/\s+/g, ' ').trim();
  return cleaned ? cleaned.slice(0, 240) : null;
}

function buildCompactSymptoms(context: ClinicalIntakeInput) {
  const complaint = context.presenting_complaint;
  const chief = cleanText(complaint.chief_complaint);
  const duration = cleanText(complaint.complaint_duration);
  const values = [
    chief && duration ? `${chief} (${duration})`.slice(0, 240) : chief,
    cleanText(complaint.associated_symptoms),
    cleanText(complaint.reason_for_visit),
  ].filter((value): value is string => Boolean(value));

  return [...new Set(values)].slice(0, 4);
}

function buildCompactVitals(context: ClinicalIntakeInput) {
  const exam = context.physical_exam;
  return {
    blood_pressure_systolic: exam.blood_pressure_systolic ?? null,
    blood_pressure_diastolic: exam.blood_pressure_diastolic ?? null,
    pulse_bpm: exam.pulse_bpm ?? null,
    temperature_c: exam.temperature_c ?? null,
    respiratory_rate: exam.respiratory_rate ?? null,
    oxygen_saturation_percent: exam.oxygen_saturation_percent ?? null,
  };
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
  analysisRunId: string,
  clinicalContext: ClinicalIntakeInput,
  sourceSummaries: CaseSourceSummaries,
  contextFlags: string[],
  qualityContext: MultisourceQualityContext,
): Promise<ClaudeReviewGenerationResult> {
  const token = getAccessToken();
  const response = await fetch(
    `${API_BASE_URL}/analysis-runs/${analysisRunId}/clinical-hypotheses/generate`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        max_hypotheses: 1,
        include_normal_results: false,
        include_needs_review_only: false,
        min_confidence: null,
        language: 'tr',
        metadata_json: {
          source: 'compact_multisource_rule_gated_evaluation',
          normal_results_excluded: true,
          patient_age: clinicalContext.patient_information.age ?? null,
          symptoms: buildCompactSymptoms(clinicalContext),
          vitals: buildCompactVitals(clinicalContext),
          source_summaries: {
            clinical: sourceSummaries.clinical.slice(0, 320),
            laboratory: sourceSummaries.laboratory.slice(0, 320),
            ultrasound: sourceSummaries.ultrasound.slice(0, 320),
          },
          context_flags: contextFlags,
          performed_studies: qualityContext.performedStudies.slice(0, 24),
          source_dates: qualityContext.sourceDates,
        },
      }),
    },
  );

  if (!response.ok) {
    const detail = await readErrorMessage(response);
    throw new Error(`AI değerlendirmesi başarısız: ${response.status} ${detail}`);
  }

  const result = (await response.json()) as ClaudeReviewGenerationResult;
  window.dispatchEvent(new Event('medicore:case-summary-updated'));
  return result;
}
