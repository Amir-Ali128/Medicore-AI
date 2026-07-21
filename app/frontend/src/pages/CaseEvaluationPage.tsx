import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import SectionCard from '../components/ui/SectionCard';
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
  return values.some((value) => value !== null && value !== undefined && String(value).trim());
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
  const match = priorities.find(([aliases]) => aliases.some((alias) => text.includes(fold(alias))));
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

function reviewText(review: ClaudeReviewGenerationResult | null) {
  if (!review) return '';
  const hypotheses = review.created_hypotheses?.length
    ? review.created_hypotheses
    : review.hypotheses ?? [];
  return [...new Set(hypotheses.map((item) => item.summary?.trim()).filter(Boolean))]
    .slice(0, 6)
    .join('\n\n');
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

function StatusCard({
  step,
  title,
  ready,
  detail,
}: {
  step: number;
  title: string;
  ready: boolean;
  detail: string;
}) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        ready
          ? 'border-emerald-200 bg-emerald-50'
          : 'border-amber-200 bg-amber-50'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Adım {step}
          </p>
          <h3 className="mt-1 font-semibold text-slate-950">{title}</h3>
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
            ready
              ? 'bg-emerald-100 text-emerald-800'
              : 'bg-amber-100 text-amber-900'
          }`}
        >
          {ready ? 'Hazır' : 'Eksik'}
        </span>
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-600">{detail}</p>
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
          setCombinedReview(readCachedReview(reviewScope(analysisRunId, uniqueReports[0].id)));
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
        .slice(0, 8),
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

  async function evaluateAllSources() {
    if (!analysisRunId || !latestReport || !clinicalContext || !allReady) {
      setError('Birleşik değerlendirme için klinik kayıt, kan analizi ve radyoloji raporu birlikte hazır olmalıdır.');
      return;
    }

    try {
      setEvaluating(true);
      setError('');
      setStatus('Klinik, laboratuvar ve radyoloji verileri birlikte değerlendiriliyor…');
      const result = await evaluateClaudeAbnormalResults(analysisRunId, 6, clinicalContext);
      const scope = reviewScope(analysisRunId, latestReport.id);
      rememberReview(scope, result);
      setCombinedReview(result);
      setStatus('Üç veri kaynağının birleşik değerlendirmesi tamamlandı ve bu vaka için saklandı.');
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
      <div className="rounded-xl border border-slate-200 bg-white p-8 text-sm text-slate-600">
        Kayıtlı klinik, laboratuvar ve radyoloji verileri yükleniyor…
      </div>
    );
  }

  const patient = clinicalContext?.patient_information;
  const combinedText = reviewText(combinedReview);

  return (
    <div className="space-y-8">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">
          Vaka değerlendirme merkezi
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">
          Bağımsız analizler ve birleşik klinik değerlendirme
        </h1>
        <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-600">
          Klinik kayıt, kan analizi ve radyoloji raporu saklanır. Kan ve radyoloji önce
          kendi modüllerinde değerlendirilir; ardından üç kaynak tek vaka olarak birlikte
          ele alınır.
        </p>
      </header>

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm leading-6 text-red-800">
          {error}
        </div>
      ) : null}
      {status ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-900">
          {status}
        </div>
      ) : null}

      <SectionCard
        title="Aktif vaka ve kayıt durumu"
        description="Her kaynak ayrı saklanır; sayfa değiştirildiğinde kayıtlar backend ve aktif vaka anahtarları üzerinden yeniden yüklenir."
      >
        <div className="mb-5 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
          <strong className="text-slate-950">
            {patient?.full_name || 'Aktif hasta adı belirtilmedi'}
          </strong>
          {' · '}
          {patient?.age ?? 'Yaş belirtilmedi'}
          {' · '}
          {sexLabel(patient?.sex)}
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <StatusCard
            step={1}
            title="Klinik kayıt"
            ready={clinicalReady}
            detail={
              clinicalReady
                ? 'Hasta veya doktor tarafından girilen klinik form saklandı.'
                : 'Önce klinik formda şikâyet, öykü veya muayene bilgisi girilmelidir.'
            }
          />
          <StatusCard
            step={2}
            title="Kan analizi"
            ready={laboratoryReady}
            detail={
              laboratoryReady
                ? `${labResults.length} yapılandırılmış sonuç kalıcı analiz kaydından yüklendi.`
                : 'Kan PDF’i yüklenmeli veya laboratuvar sonuçları manuel girilmelidir.'
            }
          />
          <StatusCard
            step={3}
            title="Radyoloji değerlendirmesi"
            ready={radiologyReady}
            detail={
              radiologyReady
                ? `${reports.length} benzersiz radyoloji raporu hasta kaydından yüklendi.`
                : 'Radyoloji raporu PDF veya metin olarak eklenmelidir.'
            }
          />
        </div>
      </SectionCard>

      <SectionCard
        title="Aşama 1 — Kaynakların ayrı değerlendirilmesi"
        description="Kan sonuçları ve radyoloji raporu önce kendi verileri içinde analiz edilir."
      >
        <div className="grid gap-5 xl:grid-cols-2">
          <div className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-slate-950">Kan sonucu değerlendirmesi</h3>
                <p className="mt-1 text-sm text-slate-600">
                  Referans, alias ve kural motoru sonucu.
                </p>
              </div>
              <Link
                to="/analysis/results"
                className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white"
              >
                Ayrıntılı kan analizini aç
              </Link>
            </div>
            {laboratoryReady ? (
              <>
                <div className="mt-5 grid grid-cols-3 gap-3 text-center">
                  <div className="rounded-lg border bg-white p-3">
                    <p className="text-2xl font-semibold text-red-700">{labCounts.high}</p>
                    <p className="text-xs text-slate-500">Yüksek</p>
                  </div>
                  <div className="rounded-lg border bg-white p-3">
                    <p className="text-2xl font-semibold text-amber-700">{labCounts.low}</p>
                    <p className="text-xs text-slate-500">Düşük</p>
                  </div>
                  <div className="rounded-lg border bg-white p-3">
                    <p className="text-2xl font-semibold text-violet-700">{labCounts.review}</p>
                    <p className="text-xs text-slate-500">Kontrol</p>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {priorityLabs.map((result) => (
                    <span
                      key={result.lab_result_id}
                      className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700"
                    >
                      {labName(result)}: {result.normalized_value} {result.unit}
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <p className="mt-5 rounded-lg border border-dashed border-amber-300 bg-white p-4 text-sm text-slate-600">
                Kaydedilmiş kan analizi bulunmuyor.
              </p>
            )}
          </div>

          <div className="rounded-xl border border-violet-200 bg-violet-50/40 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-slate-950">Radyoloji değerlendirmesi</h3>
                <p className="mt-1 text-sm text-slate-600">
                  Rapor metni, bulgular, ölçümler ve sonuç bölümü.
                </p>
              </div>
              <Link
                to="/radiology"
                className="rounded-lg bg-violet-700 px-4 py-2 text-sm font-semibold text-white"
              >
                Radyoloji bölümünü aç
              </Link>
            </div>
            {latestReport ? (
              <div className="mt-5 rounded-xl border border-violet-100 bg-white p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-violet-700">
                  {latestReport.modality} · {latestReport.body_part}
                </p>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-700">
                  {reportSummary(latestReport)}
                </p>
                <div className="mt-4 flex flex-wrap gap-2 text-xs">
                  <span className="rounded-full bg-slate-100 px-3 py-1.5 text-slate-700">
                    {latestReport.findings.length} bulgu
                  </span>
                  <span className="rounded-full bg-slate-100 px-3 py-1.5 text-slate-700">
                    {latestReport.measurements.length} ölçüm
                  </span>
                  <span className="rounded-full bg-red-50 px-3 py-1.5 text-red-700">
                    {latestReport.critical_findings.length} kritik ifade
                  </span>
                </div>
              </div>
            ) : (
              <p className="mt-5 rounded-lg border border-dashed border-amber-300 bg-white p-4 text-sm text-slate-600">
                Kaydedilmiş radyoloji raporu bulunmuyor.
              </p>
            )}
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Aşama 2 — Üç verinin birlikte değerlendirilmesi"
        description="Klinik form, yapılandırılmış kan sonuçları ve kaydedilmiş radyoloji raporu aynı vaka bağlamında değerlendirilir."
      >
        <div className="grid gap-5 lg:grid-cols-[1fr_auto] lg:items-start">
          <div>
            <p className="text-sm leading-6 text-slate-600">
              Bu aşama yalnızca üç veri kaynağı da hazır olduğunda çalışır. Önceki bağımsız
              analizler silinmez; birleşik çıktı ayrıca vaka kapsamıyla saklanır.
            </p>
            <div className="mt-4 flex flex-wrap gap-2 text-xs font-semibold">
              <span className={`rounded-full px-3 py-1.5 ${clinicalReady ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-900'}`}>
                Klinik {clinicalReady ? 'hazır' : 'eksik'}
              </span>
              <span className={`rounded-full px-3 py-1.5 ${laboratoryReady ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-900'}`}>
                Kan {laboratoryReady ? 'hazır' : 'eksik'}
              </span>
              <span className={`rounded-full px-3 py-1.5 ${radiologyReady ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-900'}`}>
                Radyoloji {radiologyReady ? 'hazır' : 'eksik'}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={evaluateAllSources}
            disabled={!allReady || evaluating}
            className="rounded-lg bg-blue-700 px-5 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {evaluating ? 'Üç kaynak değerlendiriliyor…' : 'Üç veriyi birlikte değerlendir'}
          </button>
        </div>

        {allReady ? (
          <div className="mt-6 rounded-xl border border-blue-200 bg-blue-50 p-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
                  Kural tabanlı klinik uyum
                </p>
                <h3 className="mt-1 text-xl font-semibold text-blue-950">
                  {compatibility.display_name} · {compatibility.level_label}
                </h3>
              </div>
              <p className="text-4xl font-extrabold text-blue-950">
                {compatibility.score}
                <span className="text-base font-semibold"> / 100</span>
              </p>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {compatibility.breakdown.map((item) => (
                <div key={item.domain} className="rounded-lg border border-blue-100 bg-white p-4">
                  <p className="text-xs font-semibold uppercase text-slate-500">{item.label}</p>
                  <p className="mt-2 text-xl font-semibold text-slate-950">
                    {item.score}/{item.maximum_score}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {combinedReview ? (
          <div className="mt-6 rounded-xl border border-violet-200 bg-violet-50 p-5">
            <h3 className="font-semibold text-violet-950">Birleşik AI klinik değerlendirmesi</h3>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-8 text-violet-950">
              {combinedText || 'AI değerlendirmesi oluşturuldu ancak gösterilebilir bir özet bulunamadı.'}
            </p>
          </div>
        ) : (
          <p className="mt-6 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-sm text-slate-600">
            Birleşik AI değerlendirmesi henüz çalıştırılmadı. Bağımsız kan ve radyoloji
            değerlendirmeleri bundan etkilenmez.
          </p>
        )}

        <p className="mt-5 text-xs leading-6 text-slate-500">
          Bu çıktılar tanı veya tedavi kararı değildir. Kural tabanlı uyum skoru ve AI
          değerlendirmesi hekim doğrulaması gerektiren karar destek çıktılarıdır.
        </p>
      </SectionCard>
    </div>
  );
}
