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

function formatSourceDate(value: string | null | undefined) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat('tr-TR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(parsed);
}

function labMeasuredAt(result: LabAnalysisResult) {
  const value = (result as LabAnalysisResult & { measured_at?: string | null }).measured_at;
  return typeof value === 'string' ? value : null;
}

function labRawValue(result: LabAnalysisResult) {
  const value = (result as LabAnalysisResult & { raw_value?: string | null }).raw_value;
  return typeof value === 'string' ? value.trim() : '';
}

function labValueText(result: LabAnalysisResult) {
  const raw = labRawValue(result);
  if (raw && (/\+/.test(raw) || /^(pozitif|negatif|eser|trace|positive|negative)$/iu.test(raw))) {
    return raw;
  }
  return String(result.normalized_value ?? '—');
}

function labSourceDate(results: LabAnalysisResult[]) {
  for (const result of results) {
    const formatted = formatSourceDate(labMeasuredAt(result));
    if (formatted) return formatted;
  }
  return null;
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

export function buildClinicalAiSummary(context: ClinicalIntakeInput | null) {
  if (!context) return 'Klinik bilgi bulunamadı.';

  const complaint = context.presenting_complaint;
  const exam = context.physical_exam;
  const parts = [
    clean(complaint.chief_complaint),
    clean(complaint.complaint_duration, 80),
    clean(complaint.associated_symptoms),
    clean(exam.examination_findings),
  ].filter((value): value is string => Boolean(value));

  return parts.join(' | ').slice(0, 320) || 'Kısa klinik özet yok.';
}

export function abnormalLabs(results: LabAnalysisResult[]) {
  return results.filter(
    (result) => result.result_status === 'high' || result.result_status === 'low',
  );
}

function meaningfulReference(value: string | null | undefined) {
  if (value == null || value === '') return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || Math.abs(parsed) >= 999_999_999) return null;
  return value;
}

function labReference(result: LabAnalysisResult) {
  const low = meaningfulReference(result.reference_min);
  const high = meaningfulReference(result.reference_max);
  const unit = result.unit ? ` ${result.unit}` : '';
  if (low != null && high != null) return `${low}-${high}${unit}`;
  if (high != null) return `<${high}${unit}`;
  if (low != null) return `>${low}${unit}`;
  return null;
}

function labDisplayName(result: LabAnalysisResult) {
  return result.raw_parameter_name || result.canonical_name || 'Laboratuvar parametresi';
}

export function buildLaboratorySummary(results: LabAnalysisResult[]) {
  if (results.length === 0) return 'Laboratuvar sonucu bulunamadı.';
  const abnormal = abnormalLabs(results);
  const sourceDate = labSourceDate(results);
  const datePrefix = sourceDate ? `${sourceDate} · ` : '';
  if (abnormal.length === 0) return `${datePrefix}Yüksek veya düşük laboratuvar bulgusu yok.`;

  const preview = abnormal.slice(0, 8).map((result) => {
    const direction = result.result_status === 'high' ? 'yüksek' : 'düşük';
    const reference = labReference(result);
    const unit = result.unit ? ` ${result.unit}` : '';
    return `${labDisplayName(result)}: ${labValueText(result)}${unit}${reference ? ` · ref ${reference}` : ''} (${direction})`;
  });
  const suffix = abnormal.length > preview.length ? ` +${abnormal.length - preview.length} yüksek/düşük bulgu` : '';
  return `${datePrefix}${preview.join('; ')}${suffix}`;
}

export function buildLaboratoryAiSummary(results: LabAnalysisResult[]) {
  const abnormal = abnormalLabs(results);
  const sourceDate = labSourceDate(results);
  const datePrefix = sourceDate ? `${sourceDate} · ` : '';
  if (abnormal.length === 0) return `${datePrefix}Yüksek veya düşük laboratuvar bulgusu yok.`;

  return `${datePrefix}${abnormal
    .map((result) => {
      const direction = result.result_status === 'high' ? 'yüksek' : 'düşük';
      const reference = labReference(result);
      const unit = result.unit ? ` ${result.unit}` : '';
      return `${labDisplayName(result)} ${labValueText(result)}${unit}${reference ? ` (ref ${reference})` : ''}: ${direction}`;
    })
    .join('; ')}`.slice(0, 900);
}

function metadataText(report: RadiologyReport, key: string) {
  const value = report.metadata_json?.[key];
  return typeof value === 'string' ? value : '';
}

function normalizedModality(report: RadiologyReport) {
  return [
    report.modality,
    metadataText(report, 'modality'),
    metadataText(report, 'requested_modality'),
    metadataText(report, 'detected_modality'),
    metadataText(report, 'supported_modality'),
  ]
    .filter(Boolean)
    .join(' ')
    .toUpperCase()
    .trim();
}

function ultrasoundNameEvidence(report: RadiologyReport) {
  const filename = (report.file_name ?? '').toLocaleLowerCase('tr-TR');
  return (
    filename.includes('ultrason') ||
    filename.includes('ultrasound') ||
    filename.includes('usg')
  );
}

export function isUltrasoundReport(report: RadiologyReport) {
  const modality = normalizedModality(report);
  const tokens = modality.split(/\s+/);
  return (
    modality.includes('ULTRASOUND') ||
    modality.includes('ULTRASON') ||
    modality.includes('USG') ||
    tokens.includes('US') ||
    ultrasoundNameEvidence(report)
  );
}

const RESULT_HEADING =
  /(?:^|\s)(?:SONUÇ|SONUC|İZLENİM|IZLENIM|DEĞERLENDİRME|DEGERLENDIRME|KANAAT|IMPRESSION|CONCLUSION)\s*[:\-–—]?\s*/iu;
const NEXT_SECTION_HEADING =
  /\s(?:BULGU|BULGULAR|FINDINGS|TEKNİK|TEKNIK|TECHNIQUE|KLİNİK|KLINIK|ENDİKASYON|ENDIKASYON|ÖNERİLER|ONERILER)\s*[:\-–—]?\s*/iu;

function extractUltrasoundResultText(report: RadiologyReport) {
  const impression = clean(report.impression, 1200);
  if (impression) return impression;

  const original = report.original_text?.replace(/\s+/g, ' ').trim() ?? '';
  if (!original) return null;

  const heading = RESULT_HEADING.exec(original);
  if (!heading || heading.index == null) return null;

  const start = heading.index + heading[0].length;
  const remainder = original.slice(start);
  const next = NEXT_SECTION_HEADING.exec(remainder);
  const resultText = next && next.index != null ? remainder.slice(0, next.index) : remainder;
  return clean(resultText, 1200);
}

function reportTimestamp(report: RadiologyReport) {
  const value = Date.parse(report.updated_at || report.created_at || report.report_date || '');
  return Number.isFinite(value) ? value : 0;
}

export function getLatestUltrasoundReport(reports: RadiologyReport[]) {
  const ultrasoundReports = reports.filter(isUltrasoundReport);
  if (ultrasoundReports.length === 0) return null;

  // Prefer a record that actually contains the radiologist's explicit result
  // section. A newer image-only/fallback archive must not hide an older usable
  // ultrasound report.
  return [...ultrasoundReports].sort((a, b) => {
    const aHasResult = Boolean(extractUltrasoundResultText(a));
    const bHasResult = Boolean(extractUltrasoundResultText(b));
    if (aHasResult !== bHasResult) return aHasResult ? -1 : 1;
    return reportTimestamp(b) - reportTimestamp(a);
  })[0];
}

export function buildUltrasoundSummary(report: RadiologyReport | null) {
  if (!report) return 'Ultrason raporu bulunamadı.';

  const date = formatSourceDate(report.report_date);
  const prefix = date ? `${date} · ` : '';
  const resultText = extractUltrasoundResultText(report);
  if (resultText) return `${prefix}${resultText}`;

  return `${prefix}Ultrason kaydı bulundu ancak Sonuç/İzlenim metni çıkarılamadı.`;
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
