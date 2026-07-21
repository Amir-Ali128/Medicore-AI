import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  evaluateClaudeAbnormalResults,
  type ClaudeReviewGenerationResult,
} from '../services/claudeReviewClient';
import { calculateAcuteCholecystitisCompatibility } from '../services/clinicalCompatibilityScore';
import {
  getAnalysisRunResults,
  LAST_ANALYSIS_RUN_ID_KEY,
  type ClinicalIntakeInput,
  type LabAnalysisResult,
} from '../services/labAnalysisClient';
import {
  listPatientRadiologyReports,
  type RadiologyReport,
} from '../services/radiologyClient';

const ACTIVE_CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';
const CASE_REVIEW_SCOPE_KEY = 'medicore:caseEvaluationScope:v1';
const CASE_REVIEW_RESULT_KEY = 'medicore:caseEvaluationResult:v1';

const METRIC_VISUALS = {
  clinical_findings: {
    emoji: '🩺',
    labelClass: 'text-sky-700',
    scoreClass: 'text-sky-900',
    iconClass: 'bg-sky-50 ring-sky-100',
  },
  laboratory_findings: {
    emoji: '🧪',
    labelClass: 'text-violet-700',
    scoreClass: 'text-violet-900',
    iconClass: 'bg-violet-50 ring-violet-100',
  },
  imaging_findings: {
    emoji: '🩻',
    labelClass: 'text-emerald-700',
    scoreClass: 'text-emerald-900',
    iconClass: 'bg-emerald-50 ring-emerald-100',
  },
  cross_modal_consistency: {
    emoji: '🧩',
    labelClass: 'text-amber-700',
    scoreClass: 'text-amber-900',
    iconClass: 'bg-amber-50 ring-amber-100',
  },
} as const;

const AI_ROW_EMOJIS = ['🫀', '🩸', '🛡️', '🩻', '🧠', '⚕️'];

function fold(value: string | null | undefined) {
  return (value ?? '')
    .toLocaleLowerCase('tr-TR')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/ı/g, 'i')
    .replace(/\s+/g, ' ')
    .trim();
}

function readClinicalContext(): ClinicalIntakeInput | null {
  try {
    const raw = localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY);
    return raw ? (JSON.parse(raw) as ClinicalIntakeInput) : null;
  } catch {
    return null;
  }
}

function hasClinicalContent(context: ClinicalIntakeInput | null) {
  if (!context) return false;
  const values = [
    context.patient_information.full_name,
    context.patient_information.age,
    context.patient_information.sex,
    context.presenting_complaint.reason_for_visit,
    context.presenting_complaint.chief_complaint,
    context.presenting_complaint.complaint_duration,
    context.presenting_complaint.associated_symptoms,
    context.clinical_history_details.history_of_present_illness,
    context.clinical_history_details.current_medical_conditions,
    context.physical_exam.examination_findings,
    context.physical_exam.temperature_c,
    context.physical_exam.pulse_bpm,
  ];
  return values.some(
    (value) => value !== null && value !== undefined && String(value).trim(),
  );
}

function reportFingerprint(report: RadiologyReport) {
  const original = fold(report.original_text).replace(/[^a-z0-9]+/g, ' ').trim();
  return original || `${report.modality}:${report.body_part}:${fold(report.summary)}` || report.id;
}

function latestUniqueReports(reports: RadiologyReport[]) {
  const seen = new Set<string>();
  return [...reports]
    .sort((left, right) => {
      const leftDate = Date.parse(left.created_at ?? left.report_date ?? '') || 0;
      const rightDate = Date.parse(right.created_at ?? right.report_date ?? '') || 0;
      return rightDate - leftDate;
    })
    .filter((report) => {
      const fingerprint = reportFingerprint(report);
      if (seen.has(fingerprint)) return false;
      seen.add(fingerprint);
      return true;
    });
}

function reportSummary(report: RadiologyReport | null) {
  if (!report) return '';
  if (report.summary?.trim() && report.summary !== 'Rapor özeti oluşturulamadı.') {
    return report.summary.trim();
  }
  if (report.impression?.trim()) return report.impression.trim();

  const abnormal = (Array.isArray(report.findings) ? report.findings : [])
    .filter((finding) => finding.is_critical || finding.classification === 'abnormal')
    .map((finding) => finding.text.trim())
    .filter(Boolean);
  if (abnormal.length > 0) return [...new Set(abnormal)].slice(0, 5).join(' ');

  const conclusion = report.original_text?.match(
    /(?:sonuç|sonuc|izlenim)\s*:\s*([\s\S]{1,1200})$/i,
  );
  return conclusion?.[1]?.replace(/\s+/g, ' ').trim() || report.original_text.slice(0, 900);
}

function labName(result: LabAnalysisResult) {
  return result.canonical_name ?? result.raw_parameter_name;
}

function labPriority(result: LabAnalysisResult) {
  const text = fold(
    [result.parameter_code, result.canonical_name, result.raw_parameter_name]
      .filter(Boolean)
      .join(' '),
  );
  const priorities: Array<[string[], number]> = [
    [['crp'], 120],
    [['wbc', 'lokosit', 'lökosit'], 115],
    [['notrofil', 'nötrofil', 'neutrophil', 'neu'], 110],
    [['bilirubin'], 105],
    [['ggt'], 100],
    [['alp'], 98],
    [['ast'], 92],
    [['alt'], 91],
    [['kreatinin'], 80],
    [['gfr'], 79],
    [['glukoz'], 75],
  ];
  const match = priorities.find(([aliases]) =>
    aliases.some((alias) => text.includes(fold(alias))),
  );
  const abnormalBoost = ['high', 'low'].includes(result.result_status) ? 20 : 0;
  return (match?.[1] ?? 0) + abnormalBoost;
}

function sexLabel(value: string | null | undefined) {
  const normalized = fold(value);
  if (normalized === 'female' || normalized === 'kadin') return 'Kadın';
  if (normalized === 'male' || normalized === 'erkek') return 'Erkek';
  if (normalized === 'other') return 'Diğer';
  if (normalized === 'unknown') return 'Bilinmiyor';
  return value || 'Belirtilmedi';
}

function reviewItems(review: ClaudeReviewGenerationResult | null) {
  if (!review) return [];
  const hypotheses = review.created_hypotheses?.length
    ? review.created_hypotheses
    : review.hypotheses ?? [];

  return [...new Set(
    hypotheses
      .map((item) => {
        const title = item.title?.trim();
        const summary = item.summary?.trim();
        if (title && summary && !fold(summary).startsWith(fold(title))) {
          return `${title}: ${summary}`;
        }
        return summary || title || '';
      })
      .filter(Boolean),
  )].slice(0, 6);
}

function reviewScope(analysisRunId: string, reportId: string) {
  return `${analysisRunId}:${reportId}`;
}

function readCachedReview(scope: string) {
  try {
    if (localStorage.getItem(CASE_REVIEW_SCOPE_KEY) !== scope) return null;
    const raw = localStorage.getItem(CASE_REVIEW_RESULT_KEY);
    return raw ? (JSON.parse(raw) as ClaudeReviewGenerationResult) : null;
  } catch {
    return null;
  }
}

function rememberReview(scope: string, review: ClaudeReviewGenerationResult) {
  localStorage.setItem(CASE_REVIEW_SCOPE_KEY, scope);
  localStorage.setItem(CASE_REVIEW_RESULT_KEY, JSON.stringify(review));
}

function evidenceEmoji(code: string, domain: string) {
  const byCode: Record<string, string> = {
    ruq_pain: '🩺',
    clinical_murphy: '🫁',
    fever: '🌡️',
    pain_duration: '⏱️',
    leukocytosis: '🩸',
    neutrophilia: '🧬',
    elevated_crp: '📈',
    additional_inflammation: '🔥',
    impacted_neck_stone: '🪨',
    wall_thickening: '🧱',
    sonographic_murphy: '🩻',
    pericholecystic_fluid: '💧',
    gallbladder_distension: '🎈',
    normal_bile_duct: '✅',
    clinical_lab_agreement: '🔗',
    clinical_imaging_agreement: '🧩',
    cholestatic_imaging_agreement: '⚖️',
  };
  if (byCode[code]) return byCode[code];
  if (domain === 'laboratory_findings') return '🧪';
  if (domain === 'imaging_findings') return '🩻';
  if (domain === 'cross_modal_consistency') return '🔗';
  return '🩺';
}

function MetricCard({
  emoji,
  label,
  score,
  maximum,
  labelClass,
  scoreClass,
  iconClass,
}: {
  emoji: string;
  label: string;
  score: number;
  maximum: number;
  labelClass: string;
  scoreClass: string;
  iconClass: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-3 py-4 text-center shadow-sm sm:px-4">
      <div
        className={`mx-auto flex h-11 w-11 items-center justify-center rounded-2xl text-2xl ring-1 ${iconClass}`}
        aria-hidden="true"
      >
        {emoji}
      </div>
      <p className={`mt-3 min-h-9 text-[10px] font-extrabold uppercase leading-4 tracking-wide ${labelClass}`}>
        {label}
      </p>
      <p className={`mt-2 text-2xl font-black tracking-tight ${scoreClass}`}>
        {score}
        <span className="text-base font-bold"> / {maximum}</span>
      </p>
    </div>
  );
}

function SourceCard({
  emoji,
  title,
  ready,
  detail,
  link,
  linkLabel,
}: {
  emoji: string;
  title: string;
  ready: boolean;
  detail: string;
  link: string;
  linkLabel: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-50 text-xl ring-1 ring-slate-200">
          {emoji}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-bold text-slate-950">{title}</h3>
            <span
              className={`rounded-full px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wide ${
                ready
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-amber-100 text-amber-900'
              }`}
            >
              {ready ? 'Hazır' : 'Eksik'}
            </span>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-600">{detail}</p>
          <Link
            to={link}
            className="mt-3 inline-flex rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-bold text-slate-700 transition hover:bg-slate-100"
          >
            {linkLabel} →
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function CaseEvaluationPage() {
  const [clinicalContext, setClinicalContext] = useState<ClinicalIntakeInput | null>(null);
  const [labResults, setLabResults] = useState<LabAnalysisResult[]>([]);
  const [reports, setReports] = useState<RadiologyReport[]>([]);
  const [combinedReview, setCombinedReview] =
    useState<ClaudeReviewGenerationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');

  const analysisRunId = localStorage.getItem(LAST_ANALYSIS_RUN_ID_KEY);

  useEffect(() => {
    let cancelled = false;

    async function hydrateCase() {
      try {
        setLoading(true);
        setError('');
        const context = readClinicalContext();
        const [loadedLabs, loadedReports] = await Promise.all([
          analysisRunId ? getAnalysisRunResults(analysisRunId) : Promise.resolve([]),
          listPatientRadiologyReports(),
        ]);
        if (cancelled) return;

        const uniqueReports = latestUniqueReports(loadedReports);
        setClinicalContext(context);
        setLabResults(loadedLabs);
        setReports(uniqueReports);

        if (analysisRunId && uniqueReports[0]?.id) {
          setCombinedReview(
            readCachedReview(reviewScope(analysisRunId, uniqueReports[0].id)),
          );
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Kayıtlı vaka verileri yüklenemedi.',
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void hydrateCase();
    return () => {
      cancelled = true;
    };
  }, [analysisRunId]);

  const clinicalReady = hasClinicalContent(clinicalContext);
  const laboratoryReady = Boolean(analysisRunId && labResults.length > 0);
  const radiologyReady = reports.length > 0;
  const allReady = clinicalReady && laboratoryReady && radiologyReady;
  const latestReport = reports[0] ?? null;

  const labCounts = useMemo(
    () => ({
      high: labResults.filter((item) => item.result_status === 'high').length,
      low: labResults.filter((item) => item.result_status === 'low').length,
      review: labResults.filter((item) =>
        ['needs_review', 'unknown'].includes(item.result_status),
      ).length,
    }),
    [labResults],
  );

  const priorityLabs = useMemo(
    () =>
      [...labResults]
        .filter((item) => item.result_status !== 'normal')
        .sort((left, right) => labPriority(right) - labPriority(left))
        .slice(0, 5),
    [labResults],
  );

  const compatibility = useMemo(
    () =>
      calculateAcuteCholecystitisCompatibility({
        clinicalContext,
        labResults,
        reports: reports.slice(0, 2),
      }),
    [clinicalContext, labResults, reports],
  );

  const aiItems = useMemo(() => reviewItems(combinedReview), [combinedReview]);
  const patient = clinicalContext?.patient_information;

  async function evaluateAllSources() {
    if (!analysisRunId || !latestReport || !clinicalContext || !allReady) {
      setError(
        'Birleşik değerlendirme için klinik kayıt, kan analizi ve radyoloji raporu birlikte hazır olmalıdır.',
      );
      return;
    }

    try {
      setEvaluating(true);
      setError('');
      setStatus('🧠 Klinik, laboratuvar ve radyoloji verileri birlikte değerlendiriliyor…');
      const result = await evaluateClaudeAbnormalResults(
        analysisRunId,
        6,
        clinicalContext,
      );
      const scope = reviewScope(analysisRunId, latestReport.id);
      rememberReview(scope, result);
      setCombinedReview(result);
      setStatus('✅ Üç veri kaynağının birleşik değerlendirmesi tamamlandı ve saklandı.');
    } catch (evaluationError) {
      setError(
        evaluationError instanceof Error
          ? evaluationError.message
          : 'Birleşik değerlendirme oluşturulamadı.',
      );
      setStatus('');
    } finally {
      setEvaluating(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl rounded-3xl border border-slate-200 bg-white p-8 text-sm text-slate-600 shadow-sm">
        ⏳ Kayıtlı klinik, laboratuvar ve radyoloji verileri yükleniyor…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-10">
      <header className="px-1">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.2em] text-blue-700">
              🧠 Klinik karar desteği
            </p>
            <h1 className="mt-2 text-2xl font-black tracking-tight text-[#14234b] sm:text-3xl">
              Klinik uyum skoru
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
              Tanı olasılığı değil; yapılandırılmış bulguların belirli bir klinik hipotezle
              deterministik uyumudur.
            </p>
          </div>
          <div className="rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-600 shadow-sm">
            👤 {patient?.full_name || 'Aktif hasta'} · {patient?.age ?? '—'} ·{' '}
            {sexLabel(patient?.sex)}
          </div>
        </div>
      </header>

      {error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm leading-6 text-red-800 shadow-sm">
          ⚠️ {error}
        </div>
      ) : null}
      {status ? (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm leading-6 text-emerald-900 shadow-sm">
          {status}
        </div>
      ) : null}

      <section className="overflow-hidden rounded-[28px] border border-[#cddcf4] bg-[#eef4ff] p-4 shadow-[0_18px_45px_rgba(37,99,235,0.08)] sm:p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-black uppercase tracking-[0.16em] text-blue-700">
              Değerlendirilen hipotez
            </p>
            <h2 className="mt-2 text-2xl font-black tracking-tight text-[#12204a] sm:text-3xl">
              {compatibility.display_name}
            </h2>
            <p className="mt-2 text-sm font-bold text-[#27345f]">
              {compatibility.level_label}
            </p>
          </div>

          <div className="w-full rounded-2xl border border-slate-200 bg-white px-6 py-5 text-center shadow-sm lg:w-40">
            <p className="text-5xl font-black leading-none tracking-tight text-[#172353]">
              {compatibility.score}
            </p>
            <p className="mt-2 text-sm font-bold text-[#172353]">/ 100</p>
            <span className="mt-3 inline-flex rounded-full bg-blue-50 px-3 py-1 text-[9px] font-black uppercase tracking-wide text-blue-700 ring-1 ring-blue-100">
              Genel uyum skoru
            </span>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {compatibility.breakdown.map((item) => {
            const visual = METRIC_VISUALS[item.domain];
            return (
              <MetricCard
                key={item.domain}
                emoji={visual.emoji}
                label={item.label}
                score={item.score}
                maximum={item.maximum_score}
                labelClass={visual.labelClass}
                scoreClass={visual.scoreClass}
                iconClass={visual.iconClass}
              />
            );
          })}
          <MetricCard
            emoji="🛡️"
            label="Genel uyum skoru"
            score={compatibility.score}
            maximum={compatibility.maximum_score}
            labelClass="text-blue-700"
            scoreClass="text-blue-900"
            iconClass="bg-blue-50 ring-blue-100"
          />
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          {compatibility.supporting_evidence.map((item) => (
            <span
              key={item.code}
              title={item.detail}
              className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-[#effcf7] px-3 py-2 text-xs font-bold text-[#285a50] shadow-sm"
            >
              <span aria-hidden="true">{evidenceEmoji(item.code, item.domain)}</span>
              {item.label}
              <span className="text-emerald-700">· +{item.points}</span>
            </span>
          ))}
        </div>

        <div className="mt-5 grid gap-2 sm:grid-cols-3">
          <div className="rounded-xl border border-slate-200 bg-white/75 px-4 py-3 text-xs font-bold text-slate-700">
            📋 Veri tamlığı: %{compatibility.data_completeness_percent}
          </div>
          <div className="rounded-xl border border-slate-200 bg-white/75 px-4 py-3 text-xs font-bold text-slate-700">
            ⚖️ Hesap türü: Kural tabanlı uyum
          </div>
          <div className="rounded-xl border border-slate-200 bg-white/75 px-4 py-3 text-xs font-bold text-slate-700">
            🎯 Olasılık tahmini: Hesaplanmıyor
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-[26px] border border-violet-200 bg-[#f6f1ff] shadow-[0_18px_45px_rgba(109,40,217,0.08)]">
        <div className="flex flex-col gap-4 border-b border-violet-200/70 px-5 py-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-violet-700 text-2xl text-white shadow-sm">
              🧠
            </div>
            <div>
              <h2 className="text-xl font-black text-[#2f1768]">
                Birleşik AI klinik değerlendirmesi
              </h2>
              <p className="mt-1 text-sm leading-6 text-violet-800/70">
                Klinik bilgiler, laboratuvar sonuçları ve görüntüleme bulguları birlikte
                değerlendirilir.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={evaluateAllSources}
            disabled={!allReady || evaluating}
            className="rounded-xl bg-violet-700 px-5 py-3 text-sm font-black text-white shadow-sm transition hover:bg-violet-800 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {evaluating ? '🧠 Değerlendiriliyor…' : '✨ Üç veriyi birlikte değerlendir'}
          </button>
        </div>

        {aiItems.length > 0 ? (
          <div className="divide-y divide-violet-200/70 px-5">
            {aiItems.map((item, index) => (
              <div key={`${item}-${index}`} className="flex gap-3 py-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-violet-200 bg-white text-xl shadow-sm">
                  {AI_ROW_EMOJIS[index % AI_ROW_EMOJIS.length]}
                </div>
                <p className="pt-1 text-sm font-medium leading-7 text-[#3d286f]">{item}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="px-5 py-6">
            <div className="rounded-2xl border border-dashed border-violet-300 bg-white/65 p-5 text-sm leading-7 text-violet-900">
              🧠 Birleşik AI değerlendirmesi henüz çalıştırılmadı. Klinik, kan ve radyoloji
              kayıtlarının üçü de hazır olduğunda yukarıdaki düğmeyle ikinci aşamayı
              başlatabilirsin.
            </div>
          </div>
        )}

        <div className="border-t border-violet-200/70 px-5 py-4">
          <div className="flex gap-3 rounded-2xl bg-white/65 p-4 text-xs leading-6 text-violet-900">
            <span className="text-lg" aria-hidden="true">⚠️</span>
            <p>
              Bu çıktı karar destek amaçlıdır; tanı veya tedavi kararı değildir. Hekim
              doğrulaması zorunludur.
            </p>
          </div>
        </div>
      </section>

      <section className="rounded-[26px] border border-slate-200 bg-slate-50 p-4 sm:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.16em] text-slate-500">
              Aşama 1
            </p>
            <h2 className="mt-1 text-lg font-black text-slate-950">
              Kaynakların ayrı değerlendirilmesi
            </h2>
          </div>
          <span className="rounded-full bg-white px-3 py-1.5 text-xs font-bold text-slate-500 ring-1 ring-slate-200">
            💾 Kayıtlar korunur
          </span>
        </div>

        <div className="grid gap-3 lg:grid-cols-3">
          <SourceCard
            emoji="🩺"
            title="Klinik kayıt"
            ready={clinicalReady}
            detail={
              clinicalReady
                ? 'Hasta veya doktor tarafından girilen klinik form aktif vaka içinde saklanıyor.'
                : 'Şikâyet, öykü veya muayene bilgisi eksik.'
            }
            link="/patients/demo"
            linkLabel="Klinik kaydı aç"
          />
          <SourceCard
            emoji="🧪"
            title="Kan sonucu değerlendirmesi"
            ready={laboratoryReady}
            detail={
              laboratoryReady
                ? `${labResults.length} sonuç kaydedildi · ${labCounts.high} yüksek · ${labCounts.low} düşük · ${labCounts.review} kontrol.`
                : 'Kan PDF’i yüklenmeli veya sonuçlar manuel girilmelidir.'
            }
            link="/analysis/results"
            linkLabel="Kan analizini aç"
          />
          <SourceCard
            emoji="🩻"
            title="Radyoloji değerlendirmesi"
            ready={radiologyReady}
            detail={
              latestReport
                ? `${latestReport.modality} · ${latestReport.body_part} · ${latestReport.findings.length} bulgu. ${reportSummary(latestReport).slice(0, 110)}`
                : 'Radyoloji PDF’i veya rapor metni eklenmelidir.'
            }
            link="/radiology"
            linkLabel="Radyoloji raporunu aç"
          />
        </div>

        {priorityLabs.length > 0 ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {priorityLabs.map((result) => (
              <span
                key={result.lab_result_id}
                className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-600"
              >
                🩸 {labName(result)}: {result.normalized_value} {result.unit}
              </span>
            ))}
          </div>
        ) : null}
      </section>

      <p className="text-center text-xs leading-6 text-slate-500">
        ℹ️ Not: Bu sistem doktorun yerini almaz; hekim kararını desteklemek için
        geliştirilmiştir.
      </p>
    </div>
  );
}
