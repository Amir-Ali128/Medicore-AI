import type { ClinicalIntakeInput, LabAnalysisResult } from './labAnalysisClient';
import type { RadiologyReport } from './radiologyClient';

export type CaseSourceSummaries = {
  clinical: string;
  laboratory: string;
  ultrasound: string;
};

function clean(value: string | null | undefined, max = 240) {
  const text = value?.replace(/\s+/g, ' ').trim();
  if (!text) return null;
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export function buildClinicalSummary(context: ClinicalIntakeInput | null) {
  if (!context) return 'Klinik bilgi bulunamadı.';

  const complaint = context.presenting_complaint;
  const exam = context.physical_exam;
  const parts: string[] = [];

  const chief = clean(complaint.chief_complaint);
  const duration = clean(complaint.complaint_duration, 80);
  const associated = clean(complaint.associated_symptoms);
  const examFinding = clean(exam.examination_findings);

  if (chief) parts.push(duration ? `${chief} (${duration})` : chief);
  if (associated) parts.push(`Eşlik eden: ${associated}`);
  if (examFinding) parts.push(`Muayene: ${examFinding}`);

  const vitals = [
    exam.blood_pressure_systolic != null && exam.blood_pressure_diastolic != null
      ? `TA ${exam.blood_pressure_systolic}/${exam.blood_pressure_diastolic}`
      : null,
    exam.pulse_bpm != null ? `Nabız ${exam.pulse_bpm}` : null,
    exam.temperature_c != null ? `Ateş ${exam.temperature_c}°C` : null,
    exam.oxygen_saturation_percent != null
      ? `SpO₂ %${exam.oxygen_saturation_percent}`
      : null,
  ].filter((value): value is string => Boolean(value));

  if (vitals.length > 0) parts.push(vitals.join(' · '));
  return parts.join(' | ') || 'Klinik bilgi girilmiş ancak kısa özet oluşturulamadı.';
}

function abnormalLabs(results: LabAnalysisResult[]) {
  return results.filter(
    (result) => result.result_status === 'high' || result.result_status === 'low',
  );
}

export function buildLaboratorySummary(results: LabAnalysisResult[]) {
  if (results.length === 0) return 'Laboratuvar sonucu bulunamadı.';
  const abnormal = abnormalLabs(results);
  if (abnormal.length === 0) return 'Belirgin yüksek/düşük laboratuvar bulgusu yok.';

  const preview = abnormal.slice(0, 8).map((result) => {
    const name = result.canonical_name ?? result.raw_parameter_name;
    const direction = result.result_status === 'high' ? 'yüksek' : 'düşük';
    return `${name}: ${result.normalized_value} ${result.unit} (${direction})`;
  });
  const suffix = abnormal.length > preview.length ? ` +${abnormal.length - preview.length} bulgu` : '';
  return `${preview.join('; ')}${suffix}`;
}

export function buildLaboratoryAiSummary(results: LabAnalysisResult[]) {
  const abnormal = abnormalLabs(results);
  if (abnormal.length === 0) return 'Patolojik laboratuvar bulgusu yok.';

  return abnormal
    .slice(0, 10)
    .map((result) => {
      const name = result.canonical_name ?? result.raw_parameter_name;
      return `${name} ${result.result_status === 'high' ? 'yüksek' : 'düşük'}`;
    })
    .join('; ')
    .slice(0, 320);
}

function normalizedModality(report: RadiologyReport) {
  return `${report.modality ?? ''} ${report.metadata_json?.modality ?? ''}`.toUpperCase();
}

export function isUltrasoundReport(report: RadiologyReport) {
  const modality = normalizedModality(report);
  return (
    modality.includes('ULTRASOUND') ||
    modality.includes('ULTRASON') ||
    modality.includes('USG')
  );
}

export function getLatestUltrasoundReport(reports: RadiologyReport[]) {
  return reports.find(isUltrasoundReport) ?? null;
}

export function buildUltrasoundSummary(report: RadiologyReport | null) {
  if (!report) return 'Ultrason raporu bulunamadı.';

  const source =
    clean(report.impression, 320) ||
    clean(report.summary, 320) ||
    clean(report.findings.map((finding) => finding.text).join('; '), 320);

  return source || 'Ultrason raporu mevcut ancak kısa özet oluşturulamadı.';
}

export function buildUltrasoundContextFlags(report: RadiologyReport | null) {
  if (!report) return [] as string[];

  const hasCritical =
    report.critical_findings.length > 0 ||
    report.findings.some(
      (finding) => finding.is_critical || finding.classification === 'critical',
    );
  if (hasCritical) return ['ULTRASOUND_CRITICAL_REVIEW'];

  const hasAbnormal = report.findings.some(
    (finding) => finding.classification === 'abnormal',
  );
  return hasAbnormal ? ['ULTRASOUND_ABNORMAL_REVIEW'] : [];
}
