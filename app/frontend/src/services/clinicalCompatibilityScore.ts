import type {
  ClinicalIntakeInput,
  LabAnalysisResult,
} from './labAnalysisClient';
import type { RadiologyReport } from './radiologyClient';

export type CompatibilityLevel =
  | 'very_low'
  | 'low'
  | 'moderate'
  | 'high'
  | 'very_high';

export type CompatibilityDomain =
  | 'clinical_findings'
  | 'laboratory_findings'
  | 'imaging_findings'
  | 'cross_modal_consistency';

export type CompatibilityEvidence = {
  code: string;
  label: string;
  domain: CompatibilityDomain;
  points: number;
  maximum_points: number;
  matched: boolean;
  detail: string;
};

export type CompatibilityBreakdown = {
  domain: CompatibilityDomain;
  label: string;
  score: number;
  maximum_score: number;
};

export type ClinicalCompatibilityScore = {
  hypothesis_code: 'acute_calculous_cholecystitis';
  display_name: 'Akut kalkülöz kolesistit';
  score: number;
  maximum_score: 100;
  level: CompatibilityLevel;
  level_label: string;
  score_type: 'rule_based_evidence_compatibility';
  estimated_probability: null;
  data_completeness_percent: number;
  breakdown: CompatibilityBreakdown[];
  evidence: CompatibilityEvidence[];
  supporting_evidence: CompatibilityEvidence[];
  missing_data: string[];
  requires_clinician_review: true;
  disclaimer: string;
};

type ScoreInput = {
  clinicalContext: ClinicalIntakeInput | null;
  labResults: LabAnalysisResult[];
  reports: RadiologyReport[];
};

const DOMAIN_LABELS: Record<CompatibilityDomain, string> = {
  clinical_findings: 'Klinik bulgular',
  laboratory_findings: 'Laboratuvar bulguları',
  imaging_findings: 'Görüntüleme bulguları',
  cross_modal_consistency: 'Bulgular arası tutarlılık',
};

function fold(value: string | null | undefined) {
  return (value ?? '')
    .toLocaleLowerCase('tr-TR')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/ı/g, 'i')
    .replace(/\s+/g, ' ')
    .trim();
}

function hasAny(text: string, terms: string[]) {
  return terms.some((term) => text.includes(fold(term)));
}

function hasPositiveMurphy(text: string) {
  if (!text.includes('murphy')) return false;
  return !/murphy.{0,32}(negatif|negative|yok|saptanmadi|izlenmedi)/.test(text);
}

function findLabResult(results: LabAnalysisResult[], aliases: string[]) {
  return results.find((result) => {
    const haystack = fold(
      [result.parameter_code, result.canonical_name, result.raw_parameter_name]
        .filter(Boolean)
        .join(' '),
    );
    return aliases.some((alias) => haystack.includes(fold(alias)));
  });
}

function isHigh(result: LabAnalysisResult | undefined) {
  return result?.result_status === 'high';
}

function clinicalText(context: ClinicalIntakeInput | null) {
  if (!context) return '';

  return fold(
    [
      context.presenting_complaint.reason_for_visit,
      context.presenting_complaint.chief_complaint,
      context.presenting_complaint.complaint_duration,
      context.presenting_complaint.associated_symptoms,
      context.clinical_history_details.history_of_present_illness,
      context.clinical_history_details.current_medical_conditions,
      context.physical_exam.examination_findings,
      context.imaging_results.ultrasound,
    ]
      .filter(Boolean)
      .join(' '),
  );
}

function imagingText(reports: RadiologyReport[]) {
  return fold(
    reports
      .flatMap((report) => [
        report.original_text,
        report.summary,
        report.impression,
        ...(Array.isArray(report.findings)
          ? report.findings.map((finding) => finding.text)
          : []),
      ])
      .filter(Boolean)
      .join(' '),
  );
}

function getDurationHours(context: ClinicalIntakeInput | null, text: string) {
  const explicitDuration = fold(context?.presenting_complaint.complaint_duration);
  const candidate = `${explicitDuration} ${text}`;
  const hourMatch = candidate.match(/(\d+(?:[.,]\d+)?)\s*(saat|hour)/);
  if (hourMatch) return Number.parseFloat(hourMatch[1].replace(',', '.'));

  const dayMatch = candidate.match(/(\d+(?:[.,]\d+)?)\s*(gun|day)/);
  if (dayMatch) return Number.parseFloat(dayMatch[1].replace(',', '.')) * 24;

  return null;
}

function evidence(
  code: string,
  label: string,
  domain: CompatibilityDomain,
  points: number,
  maximumPoints: number,
  matched: boolean,
  detail: string,
): CompatibilityEvidence {
  return {
    code,
    label,
    domain,
    points: matched ? points : 0,
    maximum_points: maximumPoints,
    matched,
    detail,
  };
}

function scoreLevel(
  score: number,
): Pick<ClinicalCompatibilityScore, 'level' | 'level_label'> {
  if (score >= 85) return { level: 'very_high', level_label: 'Çok yüksek uyum' };
  if (score >= 70) return { level: 'high', level_label: 'Yüksek uyum' };
  if (score >= 50) return { level: 'moderate', level_label: 'Orta uyum' };
  if (score >= 25) return { level: 'low', level_label: 'Düşük uyum' };
  return { level: 'very_low', level_label: 'Çok düşük uyum' };
}

function calculateCompleteness(input: ScoreInput) {
  const clinicalAvailable = Boolean(clinicalText(input.clinicalContext));
  const labsAvailable = input.labResults.length > 0;
  const imagingAvailable = Boolean(imagingText(input.reports));
  const crossModalAvailable =
    [clinicalAvailable, labsAvailable, imagingAvailable].filter(Boolean).length >= 2;

  const score =
    (clinicalAvailable ? 30 : 0) +
    (labsAvailable ? 25 : 0) +
    (imagingAvailable ? 40 : 0) +
    (crossModalAvailable ? 5 : 0);

  const missing: string[] = [];
  if (!clinicalAvailable) missing.push('Klinik öykü ve fizik muayene bulguları');
  if (!labsAvailable) missing.push('Yapılandırılmış laboratuvar sonuçları');
  if (!imagingAvailable) missing.push('Ultrason veya görüntüleme raporu');

  return { score, missing };
}

function measuredGallbladderWallThickening(text: string) {
  const match = text.match(
    /(?:safra kesesi\s+)?duvar kalinligi\s*(?:[:=]|olarak)?\s*(\d+(?:[.,]\d+)?)\s*mm/,
  );
  if (!match) return false;
  const value = Number.parseFloat(match[1].replace(',', '.'));
  return Number.isFinite(value) && value > 3;
}

export function calculateAcuteCholecystitisCompatibility(
  input: ScoreInput,
): ClinicalCompatibilityScore {
  const clinical = clinicalText(input.clinicalContext);
  const imaging = imagingText(input.reports);
  const durationHours = getDurationHours(input.clinicalContext, clinical);
  const temperature = input.clinicalContext?.physical_exam.temperature_c ?? null;

  const wbc = findLabResult(input.labResults, ['wbc', 'lökosit', 'lokosit', 'leukocyte']);
  const neutrophil = findLabResult(input.labResults, [
    'neutrophil',
    'nötrofil',
    'notrofil',
    'neu',
    'parçalı mutlak',
    'parcali mutlak',
  ]);
  const crp = findLabResult(input.labResults, ['crp', 'c-reaktif', 'c reaktif']);
  const procalcitonin = findLabResult(input.labResults, [
    'prokalsitonin',
    'procalcitonin',
  ]);
  const esr = findLabResult(input.labResults, ['esr', 'sedim', 'sedimentasyon']);
  const bilirubin = findLabResult(input.labResults, [
    'total bilirubin',
    'bilirubin total',
    'tbil',
  ]);
  const directBilirubin = findLabResult(input.labResults, [
    'direkt bilirubin',
    'direct bilirubin',
    'dbil',
  ]);
  const alp = findLabResult(input.labResults, ['alp', 'alkalen fosfataz']);
  const ggt = findLabResult(input.labResults, ['ggt', 'gama glutamil', 'gamma glutamyl']);

  const rightUpperQuadrantPain = hasAny(clinical, [
    'sağ üst kadran',
    'sag ust kadran',
    'right upper quadrant',
    'ruq',
    'sağ subkostal',
    'sag subkostal',
  ]);
  const murphyPositive = hasPositiveMurphy(clinical);
  const fever =
    (temperature !== null && Number(temperature) >= 38) ||
    hasAny(clinical, ['ateş', 'ates', 'fever']);
  const durationOverSixHours = durationHours !== null && durationHours > 6;
  const durationPoints = durationHours !== null && durationHours > 24 ? 5 : 4;

  const impactedNeckStone =
    hasAny(imaging, ['impakte', 'hareketsiz yerleşimli', 'hareketsiz yerlesimli']) &&
    hasAny(imaging, ['kese boynu', 'safra kesesi boynu', 'gallbladder neck']) &&
    hasAny(imaging, ['taş', 'tas', 'kalkül', 'kalkul', 'stone']);
  const wallThickening =
    measuredGallbladderWallThickening(imaging) ||
    hasAny(imaging, [
      'duvar kalınlaş',
      'duvar kalinlas',
      'duvar kalınlığı art',
      'duvar kalinligi art',
      'wall thickening',
    ]);
  const sonographicMurphy =
    hasPositiveMurphy(imaging) && hasAny(imaging, ['sonografik', 'ultrason', 'prob']);
  const pericholecysticFluid =
    /perikolesistik.{0,45}(sivi|serbest sivi)/.test(imaging) ||
    /pericholecystic.{0,45}fluid/.test(imaging);
  const minimalPericholecysticFluid =
    pericholecysticFluid && hasAny(imaging, ['minimal', 'ince tabaka', 'az miktarda']);
  const gallbladderDistension = hasAny(imaging, [
    'safra kesesi distandü',
    'safra kesesi distandu',
    'safra kesesi distansiyonu',
    'gallbladder distension',
  ]);
  const noBileDuctDilatation = hasAny(imaging, [
    'safra yollarında dilatasyon saptanmamıştır',
    'safra yollarinda dilatasyon saptanmamistir',
    'koledok normal sınırlarda',
    'koledok normal sinirlarda',
    'bile duct dilatation yok',
  ]);
  const noCommonBileDuctStone = hasAny(imaging, [
    'koledok içerisinde kalkül saptanmamıştır',
    'koledok icerisinde kalkul saptanmamistir',
    'koledokta taş saptanmadı',
    'koledokta tas saptanmadi',
    'common bile duct stone yok',
  ]);
  const bileDuctDilatation =
    !noBileDuctDilatation &&
    ((hasAny(imaging, ['koledok', 'safra yolu', 'safra yollari']) &&
      hasAny(imaging, ['dilate', 'dilatasyon', 'geniş', 'genis', 'belirgin'])) ||
      /koledok.{0,30}\b([7-9]|\d{2,})(?:[.,]\d+)?\s*mm/.test(imaging));

  const inflammatoryLabSupport = isHigh(wbc) || isHigh(neutrophil) || isHigh(crp);
  const keyImagingSupport =
    impactedNeckStone ||
    wallThickening ||
    sonographicMurphy ||
    pericholecysticFluid ||
    gallbladderDistension;
  const cholestaticLabSupport =
    isHigh(bilirubin) ||
    isHigh(directBilirubin) ||
    isHigh(alp) ||
    isHigh(ggt);
  const additionalInflammationPoints = isHigh(procalcitonin) ? 3 : isHigh(esr) ? 2 : 0;

  const evidenceItems: CompatibilityEvidence[] = [
    evidence('ruq_pain', 'Sağ üst kadran ağrısı veya hassasiyeti', 'clinical_findings', 8, 8, rightUpperQuadrantPain, rightUpperQuadrantPain ? 'Klinik metinde sağ üst kadran ağrısı/hassasiyeti bulundu.' : 'Sağ üst kadran ağrısı açıkça bulunamadı.'),
    evidence('clinical_murphy', 'Klinik Murphy bulgusu', 'clinical_findings', 12, 12, murphyPositive, murphyPositive ? 'Murphy bulgusu pozitif olarak yorumlandı.' : 'Pozitif Murphy bulgusu bulunamadı.'),
    evidence('fever', 'Ateş', 'clinical_findings', 5, 5, fever, fever ? `Ateş desteği bulundu${temperature !== null ? ` (${temperature} °C)` : ''}.` : 'Ateş desteği bulunamadı.'),
    evidence('pain_duration', 'Ağrının altı saatten uzun sürmesi', 'clinical_findings', durationPoints, 5, durationOverSixHours, durationOverSixHours ? `Semptom süresi yaklaşık ${durationHours} saat.` : 'Altı saati aşan semptom süresi doğrulanamadı.'),

    evidence('leukocytosis', 'Lökositoz', 'laboratory_findings', 8, 8, isHigh(wbc), isHigh(wbc) ? `Lökosit yüksek (${wbc?.normalized_value} ${wbc?.unit}).` : 'Yüksek lökosit sonucu bulunamadı.'),
    evidence('neutrophilia', 'Nötrofili', 'laboratory_findings', 4, 4, isHigh(neutrophil), isHigh(neutrophil) ? `Nötrofil yüksek (${neutrophil?.normalized_value} ${neutrophil?.unit}).` : 'Nötrofili bulunamadı.'),
    evidence('elevated_crp', 'CRP yüksekliği', 'laboratory_findings', 10, 10, isHigh(crp), isHigh(crp) ? `CRP yüksek (${crp?.normalized_value} ${crp?.unit}).` : 'Yüksek CRP sonucu bulunamadı.'),
    evidence('additional_inflammation', 'Ek inflamasyon desteği', 'laboratory_findings', additionalInflammationPoints, 3, additionalInflammationPoints > 0, isHigh(procalcitonin) ? `Prokalsitonin yüksek (${procalcitonin?.normalized_value} ${procalcitonin?.unit}).` : isHigh(esr) ? `Sedimentasyon yüksek (${esr?.normalized_value} ${esr?.unit}).` : 'Ek inflamasyon belirteci desteği bulunamadı.'),

    evidence('impacted_neck_stone', 'Safra kesesi boynunda impakte taş', 'imaging_findings', 10, 10, impactedNeckStone, impactedNeckStone ? 'Kese boynunda impakte/hareketsiz kalkül ifadesi bulundu.' : 'Kese boynunda impakte taş doğrulanamadı.'),
    evidence('wall_thickening', 'Safra kesesi duvar kalınlaşması', 'imaging_findings', 8, 8, wallThickening, wallThickening ? 'Duvar kalınlığı 3 mm üzerinde veya kalınlaşmış olarak raporlandı.' : 'Duvar kalınlaşması bulunamadı.'),
    evidence('sonographic_murphy', 'Sonografik Murphy bulgusu', 'imaging_findings', 8, 8, sonographicMurphy, sonographicMurphy ? 'Sonografik Murphy bulgusu pozitif.' : 'Pozitif sonografik Murphy bulgusu bulunamadı.'),
    evidence('pericholecystic_fluid', 'Perikolesistik sıvı', 'imaging_findings', minimalPericholecysticFluid ? 6 : 7, 7, pericholecysticFluid, pericholecysticFluid ? `${minimalPericholecysticFluid ? 'Minimal ' : ''}perikolesistik sıvı bulundu.` : 'Perikolesistik sıvı bulunamadı.'),
    evidence('gallbladder_distension', 'Safra kesesi distansiyonu', 'imaging_findings', 5, 5, gallbladderDistension, gallbladderDistension ? 'Safra kesesi distansiyonu raporlandı.' : 'Safra kesesi distansiyonu bulunamadı.'),
    evidence('normal_bile_duct', 'Koledokta taş veya dilatasyon olmaması', 'imaging_findings', (noBileDuctDilatation ? 1 : 0) + (noCommonBileDuctStone ? 1 : 0), 2, noBileDuctDilatation || noCommonBileDuctStone, [noBileDuctDilatation ? 'Safra yolu dilatasyonu yok.' : '', noCommonBileDuctStone ? 'Koledok taşı yok.' : ''].filter(Boolean).join(' ') || 'Koledok için destekleyici negatif bulgu bulunamadı.'),

    evidence('clinical_lab_agreement', 'Klinik inflamasyon ile laboratuvar uyumu', 'cross_modal_consistency', 2, 2, (fever || rightUpperQuadrantPain || murphyPositive) && inflammatoryLabSupport, inflammatoryLabSupport ? 'Klinik inflamasyon bulgularına lökosit/nötrofil/CRP yüksekliği eşlik ediyor.' : 'Klinik ve inflamatuvar laboratuvar uyumu doğrulanamadı.'),
    evidence('clinical_imaging_agreement', 'Klinik lokalizasyon ile görüntüleme uyumu', 'cross_modal_consistency', 2, 2, (rightUpperQuadrantPain || murphyPositive) && keyImagingSupport, keyImagingSupport ? 'Sağ üst kadran/Murphy bulguları safra kesesi görüntüleme bulgularıyla aynı odağı destekliyor.' : 'Klinik lokalizasyon ile görüntüleme uyumu doğrulanamadı.'),
    evidence('cholestatic_imaging_agreement', 'Kolestatik laboratuvar ile safra yolu uyumu', 'cross_modal_consistency', 1, 1, cholestaticLabSupport && bileDuctDilatation, cholestaticLabSupport && bileDuctDilatation ? 'Kolestatik laboratuvar yüksekliği ile koledok/safra yolu genişliği birlikte bulundu.' : 'Kolestatik laboratuvar ve safra yolu görüntüleme uyumu doğrulanamadı.'),
  ];

  const breakdown: CompatibilityBreakdown[] = (
    [
      'clinical_findings',
      'laboratory_findings',
      'imaging_findings',
      'cross_modal_consistency',
    ] as CompatibilityDomain[]
  ).map((domain) => ({
    domain,
    label: DOMAIN_LABELS[domain],
    score: evidenceItems
      .filter((item) => item.domain === domain)
      .reduce((total, item) => total + item.points, 0),
    maximum_score: evidenceItems
      .filter((item) => item.domain === domain)
      .reduce((total, item) => total + item.maximum_points, 0),
  }));

  const rawScore = breakdown.reduce((total, item) => total + item.score, 0);
  const score = Math.max(0, Math.min(100, rawScore));
  const completeness = calculateCompleteness(input);
  const level = scoreLevel(score);

  return {
    hypothesis_code: 'acute_calculous_cholecystitis',
    display_name: 'Akut kalkülöz kolesistit',
    score,
    maximum_score: 100,
    ...level,
    score_type: 'rule_based_evidence_compatibility',
    estimated_probability: null,
    data_completeness_percent: completeness.score,
    breakdown,
    evidence: evidenceItems,
    supporting_evidence: evidenceItems.filter((item) => item.matched && item.points > 0),
    missing_data: completeness.missing,
    requires_clinician_review: true,
    disclaimer:
      'Bu puan tanı olasılığı değildir. Yapılandırılmış bulguların akut kalkülöz kolesistit hipoteziyle uyumunu gösterir ve hekim değerlendirmesinin yerine geçmez.',
  };
}
