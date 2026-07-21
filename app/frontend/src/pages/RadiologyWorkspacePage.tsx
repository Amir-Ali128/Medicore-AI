import { useEffect, useState, type FormEvent } from 'react';

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
  createManualRadiologyReport,
  listPatientRadiologyReports,
  uploadRadiologyReportPdf,
  type RadiologyReport,
} from '../services/radiologyClient';

const INPUT_CLASS =
  'mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950';
const ACTIVE_CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';
const LAST_COMBINED_REVIEW_SCOPE_KEY = 'medicore:lastCombinedReviewScope';
const LAST_COMBINED_REVIEW_KEY = 'medicore:lastCombinedReview';

const inFlightReviewRequests = new Map<
  string,
  Promise<ClaudeReviewGenerationResult>
>();

function reportSummary(report: RadiologyReport | null) {
  if (!report) return '';

  const technicalSummary = report.summary?.trim() ?? '';
  const looksLikeStatistics = /\b\d+\s+(klinik bulgu|bulgu cümlesi|ölçüm|kritik uyarı)/i.test(
    technicalSummary,
  );

  if (!looksLikeStatistics && technicalSummary) return technicalSummary;

  const priorityFindings = (Array.isArray(report.findings) ? report.findings : [])
    .filter((item) => item.is_critical || item.classification === 'abnormal')
    .map((item) => item.text.trim())
    .filter(Boolean);

  const sentences = [...priorityFindings];
  if (report.impression?.trim()) sentences.push(report.impression.trim());

  return [...new Set(sentences)].slice(0, 6).join(' ');
}

function reportUrgency(report: RadiologyReport | null) {
  if (!report) return 'RUTİN';
  if (Array.isArray(report.critical_findings) && report.critical_findings.length > 0) {
    return 'ACİL';
  }

  const hasAbnormalFinding = Array.isArray(report.findings)
    ? report.findings.some((finding) => finding.classification === 'abnormal')
    : false;

  return hasAbnormalFinding ? 'DİKKAT' : 'RUTİN';
}

function readClinicalContext(): ClinicalIntakeInput | null {
  try {
    const raw = localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY);
    return raw ? (JSON.parse(raw) as ClinicalIntakeInput) : null;
  } catch {
    return null;
  }
}

function sortLatestReports(reports: RadiologyReport[]) {
  return [...reports]
    .sort((left, right) => {
      const leftDate = Date.parse(left.report_date ?? left.created_at ?? '') || 0;
      const rightDate = Date.parse(right.report_date ?? right.created_at ?? '') || 0;
      return rightDate - leftDate;
    })
    .slice(0, 2);
}

function reviewSummary(review: ClaudeReviewGenerationResult | null) {
  if (!review) return '';

  const hypotheses = review.created_hypotheses?.length
    ? review.created_hypotheses
    : review.hypotheses ?? [];

  return [...new Set(hypotheses.map((item) => item.summary?.trim()).filter(Boolean))]
    .slice(0, 4)
    .join('\n\n');
}

function reviewScope(analysisRunId: string, latestReportId: string | null) {
  return `${analysisRunId}:${latestReportId ?? 'no-radiology-report'}`;
}

function readCachedReview(scope: string): ClaudeReviewGenerationResult | null {
  try {
    if (localStorage.getItem(LAST_COMBINED_REVIEW_SCOPE_KEY) !== scope) {
      return null;
    }

    const raw = localStorage.getItem(LAST_COMBINED_REVIEW_KEY);
    return raw ? (JSON.parse(raw) as ClaudeReviewGenerationResult) : null;
  } catch {
    return null;
  }
}

function rememberReview(
  scope: string,
  review: ClaudeReviewGenerationResult,
): ClaudeReviewGenerationResult {
  localStorage.setItem(LAST_COMBINED_REVIEW_SCOPE_KEY, scope);
  localStorage.setItem(LAST_COMBINED_REVIEW_KEY, JSON.stringify(review));
  return review;
}

function loadOrCreateReview(
  analysisRunId: string,
  latestReportId: string | null,
  context: ClinicalIntakeInput,
): Promise<ClaudeReviewGenerationResult> {
  const scope = reviewScope(analysisRunId, latestReportId);
  const cached = readCachedReview(scope);
  if (cached) return Promise.resolve(cached);

  const existing = inFlightReviewRequests.get(scope);
  if (existing) return existing;

  const request = evaluateClaudeAbnormalResults(
    analysisRunId,
    5,
    context,
  )
    .then((review) => rememberReview(scope, review))
    .finally(() => {
      inFlightReviewRequests.delete(scope);
    });

  inFlightReviewRequests.set(scope, request);
  return request;
}

function LabResultCard({ result }: { result: LabAnalysisResult }) {
  const name = result.canonical_name ?? result.raw_parameter_name;
  const statusLabel =
    result.result_status === 'high'
      ? 'Yüksek'
      : result.result_status === 'low'
        ? 'Düşük'
        : result.result_status === 'needs_review'
          ? 'İnceleme gerekli'
          : 'Normal';

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-950">{name}</p>
          <p className="mt-1 text-sm text-slate-700">
            {result.normalized_value} {result.unit}
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700">
          {statusLabel}
        </span>
      </div>
      {result.reason ? (
        <p className="mt-2 text-xs leading-5 text-slate-500">{result.reason}</p>
      ) : null}
    </div>
  );
}

function ReportCard({ report, index }: { report: RadiologyReport; index: number }) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold text-slate-950">Rapor {index + 1}</h3>
        <span className="text-xs font-medium text-slate-500">
          {report.modality} · {report.body_part}
        </span>
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-700">
        {reportSummary(report) || report.impression || 'Rapor özeti oluşturulamadı.'}
      </p>
      {report.report_date ? (
        <p className="mt-3 text-xs text-slate-500">Tarih: {report.report_date}</p>
      ) : null}
    </article>
  );
}

export default function RadiologyWorkspacePage() {
  const [mode, setMode] = useState<'manual' | 'pdf'>('manual');
  const [reportText, setReportText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<RadiologyReport | null>(null);
  const [clinicalContext, setClinicalContext] = useState<ClinicalIntakeInput | null>(null);
  const [labResults, setLabResults] = useState<LabAnalysisResult[]>([]);
  const [reports, setReports] = useState<RadiologyReport[]>([]);
  const [combinedReview, setCombinedReview] =
    useState<ClaudeReviewGenerationResult | null>(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function hydrateStoredCase() {
      const context = readClinicalContext();
      const analysisRunId = localStorage.getItem(LAST_ANALYSIS_RUN_ID_KEY);

      if (!cancelled) {
        setClinicalContext(context);
        setStatus('Kayıtlı klinik, laboratuvar ve radyoloji verileri yükleniyor…');
        setError('');
      }

      try {
        const [allReports, latestLabResults] = await Promise.all([
          listPatientRadiologyReports(),
          analysisRunId ? getAnalysisRunResults(analysisRunId) : Promise.resolve([]),
        ]);

        if (cancelled) return;

        const latestTwoReports = sortLatestReports(allReports);
        setReports(latestTwoReports);
        setResult(latestTwoReports[0] ?? null);
        setLabResults(latestLabResults);

        if (!analysisRunId) {
          setStatus('Görüntüleme kaydı yüklendi; bu hasta için laboratuvar analizi bulunamadı.');
          return;
        }

        if (!context) {
          setStatus('Kan ve radyoloji verileri yüklendi; klinik hasta bağlamı bulunamadı.');
          return;
        }

        if (latestLabResults.length === 0) {
          setStatus('Klinik ve radyoloji verileri yüklendi; yapılandırılmış kan sonucu bulunamadı.');
          return;
        }

        const review = await loadOrCreateReview(
          analysisRunId,
          latestTwoReports[0]?.id ?? null,
          context,
        );

        if (cancelled) return;

        setCombinedReview(review);
        setStatus(
          'Kayıtlı kan sonuçları, klinik hasta bilgileri ve görüntüleme raporları birlikte yüklendi.',
        );
      } catch (loadError) {
        if (cancelled) return;

        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Kayıtlı birleşik hasta verileri yüklenemedi.',
        );
        setStatus('');
      }
    }

    void hydrateStoredCase();

    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setStatus('');
    setCombinedReview(null);

    try {
      const report =
        mode === 'manual'
          ? await createManualRadiologyReport({
              reportDate: new Date().toISOString().slice(0, 10),
              modality: null,
              bodyPart: null,
              reportText,
            })
          : file
            ? await uploadRadiologyReportPdf(file, {
                reportDate: new Date().toISOString().slice(0, 10),
                modality: null,
                bodyPart: null,
              })
            : (() => {
                throw new Error('Önce bir PDF dosyası seçmelisin.');
              })();

      setResult(report);

      const context = readClinicalContext();
      setClinicalContext(context);

      const allReports = await listPatientRadiologyReports();
      const latestTwoReports = sortLatestReports(allReports);
      setReports(latestTwoReports);

      const analysisRunId = localStorage.getItem(LAST_ANALYSIS_RUN_ID_KEY);
      if (!analysisRunId) {
        setLabResults([]);
        setStatus(
          'Rapor kaydedildi. Kan sonuçları eklenince birleşik değerlendirme de oluşturulacak.',
        );
        return;
      }

      const latestLabResults = await getAnalysisRunResults(analysisRunId);
      setLabResults(latestLabResults);

      if (!context || latestLabResults.length === 0) {
        setStatus(
          'Rapor kaydedildi; birleşik AI değerlendirmesi için klinik bağlam ve yapılandırılmış kan sonuçları gerekli.',
        );
        return;
      }

      const scope = reviewScope(
        analysisRunId,
        latestTwoReports[0]?.id ?? report.id,
      );
      const review = rememberReview(
        scope,
        await evaluateClaudeAbnormalResults(analysisRunId, 5, context),
      );

      setCombinedReview(review);
      setStatus(
        'Kan sonuçları, klinik hasta bilgileri ve son iki rapor tek sayfada birlikte değerlendirildi.',
      );
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'Birleşik değerlendirme başarısız.',
      );
    } finally {
      setBusy(false);
    }
  }

  const summary = reportSummary(result);
  const urgency = reportUrgency(result);
  const combinedSummary = reviewSummary(combinedReview);
  const abnormalLabResults = labResults.filter((item) =>
    ['high', 'low', 'needs_review'].includes(item.result_status),
  );
  const displayedLabResults = (
    abnormalLabResults.length > 0 ? abnormalLabResults : labResults
  ).slice(0, 8);
  const patient = clinicalContext?.patient_information;
  const complaint = clinicalContext?.presenting_complaint;
  const history = clinicalContext?.clinical_history_details;
  const urgencyClass =
    urgency === 'ACİL'
      ? 'border-red-300 bg-red-600 text-white'
      : urgency === 'DİKKAT'
        ? 'border-amber-300 bg-amber-100 text-amber-950'
        : 'border-emerald-300 bg-emerald-100 text-emerald-950';
  const scoredReports = reports.length > 0 ? reports : result ? [result] : [];
  const compatibility = calculateAcuteCholecystitisCompatibility({
    clinicalContext,
    labResults,
    reports: scoredReports,
  });
  const compatibilityClass =
    compatibility.score >= 85
      ? 'border-emerald-300 bg-emerald-50 text-emerald-950'
      : compatibility.score >= 70
        ? 'border-blue-300 bg-blue-50 text-blue-950'
        : compatibility.score >= 50
          ? 'border-amber-300 bg-amber-50 text-amber-950'
          : 'border-slate-300 bg-slate-50 text-slate-950';

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">
          Raporlama
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">
          Birleşik hasta değerlendirmesi
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Kan sonuçlarını, klinik hasta bilgilerini ve son iki görüntüleme raporunu
          aynı sayfada değerlendirir.
        </p>
      </header>

      <form onSubmit={submit}>
        <SectionCard
          title="Yeni görüntüleme raporu"
          description="Metni yapıştır veya PDF yükle."
        >
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setMode('manual')}
              className="rounded-lg border px-4 py-2 text-sm font-semibold"
            >
              Rapor metni
            </button>
            <button
              type="button"
              onClick={() => setMode('pdf')}
              className="rounded-lg border px-4 py-2 text-sm font-semibold"
            >
              PDF yükle
            </button>
          </div>

          {mode === 'manual' ? (
            <textarea
              required
              minLength={10}
              rows={12}
              value={reportText}
              onChange={(event) => setReportText(event.target.value)}
              className={`${INPUT_CLASS} mt-5 resize-y`}
              placeholder="Rapor metnini buraya yapıştır..."
            />
          ) : (
            <input
              required
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className={`${INPUT_CLASS} mt-5`}
            />
          )}

          {status ? (
            <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
              {status}
            </p>
          ) : null}
          {error ? (
            <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={busy}
            className="mt-5 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-60"
          >
            {busy
              ? 'Tüm veriler değerlendiriliyor…'
              : 'Kaydet ve tüm verilerle değerlendir'}
          </button>
        </SectionCard>
      </form>

      {result ? (
        <div className="space-y-6">
          <SectionCard
            title="Yeni raporun özeti"
            description={`${result.modality} · ${result.body_part}`}
          >
            <div className="space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span
                  className={`rounded-full border px-4 py-2 text-sm font-extrabold tracking-wide ${urgencyClass}`}
                >
                  Klinik öncelik: {urgency}
                </span>
                <span className="text-xs text-slate-500">
                  Hekim doğrulaması zorunludur.
                </span>
              </div>
              <section className="rounded-xl border border-blue-200 bg-blue-50 p-5">
                <h2 className="font-semibold text-blue-950">AI radyoloji özeti</h2>
                <p className="mt-3 text-sm leading-7 text-blue-950">
                  {summary || 'Bu rapor için özet oluşturulamadı.'}
                </p>
              </section>
            </div>
          </SectionCard>

          <div className="grid gap-6 xl:grid-cols-2">
            <SectionCard
              title="Klinik hasta bilgileri"
              description="Aktif hasta kaydından alınır."
            >
              {patient || complaint || history ? (
                <div className="space-y-4 text-sm text-slate-700">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <p>
                      <span className="font-semibold text-slate-950">Hasta:</span>{' '}
                      {patient?.full_name || 'Belirtilmedi'}
                    </p>
                    <p>
                      <span className="font-semibold text-slate-950">
                        Yaş / cinsiyet:
                      </span>{' '}
                      {[patient?.age, patient?.sex].filter(Boolean).join(' / ') ||
                        'Belirtilmedi'}
                    </p>
                  </div>
                  <p>
                    <span className="font-semibold text-slate-950">
                      Başvuru nedeni:
                    </span>{' '}
                    {complaint?.reason_for_visit ||
                      complaint?.chief_complaint ||
                      'Belirtilmedi'}
                  </p>
                  <p>
                    <span className="font-semibold text-slate-950">Semptomlar:</span>{' '}
                    {complaint?.associated_symptoms || 'Belirtilmedi'}
                  </p>
                  <p>
                    <span className="font-semibold text-slate-950">
                      Klinik öykü:
                    </span>{' '}
                    {history?.history_of_present_illness ||
                      history?.current_medical_conditions ||
                      'Belirtilmedi'}
                  </p>
                </div>
              ) : (
                <p className="text-sm text-slate-600">
                  Aktif klinik hasta bilgisi bulunamadı.
                </p>
              )}
            </SectionCard>

            <SectionCard
              title="Kan sonuçları"
              description="Öncelikle anormal sonuçlar gösterilir."
            >
              {displayedLabResults.length > 0 ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  {displayedLabResults.map((item) => (
                    <LabResultCard key={item.lab_result_id} result={item} />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-600">
                  Bu hasta için analiz edilmiş kan sonucu bulunamadı.
                </p>
              )}
            </SectionCard>
          </div>

          <SectionCard
            title="Son iki görüntüleme raporu"
            description="En güncel iki rapor birlikte gösterilir."
          >
            {reports.length > 0 ? (
              <div className="grid gap-4 lg:grid-cols-2">
                {reports.map((report, index) => (
                  <ReportCard key={report.id} report={report} index={index} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-600">
                Görüntüleme raporu bulunamadı.
              </p>
            )}
          </SectionCard>

          <SectionCard
            title="Klinik uyum skoru"
            description="Tanı olasılığı değil; yapılandırılmış bulguların belirli bir klinik hipotezle deterministik uyumudur."
          >
            <div className={`rounded-xl border p-5 ${compatibilityClass}`}>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-xs font-extrabold uppercase tracking-wide">
                    Değerlendirilen hipotez
                  </p>
                  <h2 className="mt-2 text-xl font-semibold">
                    {compatibility.display_name}
                  </h2>
                  <p className="mt-2 text-sm font-semibold">
                    {compatibility.level_label}
                  </p>
                </div>
                <div className="rounded-xl border border-current/20 bg-white/70 px-6 py-4 text-center">
                  <p className="text-4xl font-black">{compatibility.score}</p>
                  <p className="mt-1 text-sm font-semibold">
                    / {compatibility.maximum_score}
                  </p>
                </div>
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {compatibility.breakdown.map((item) => (
                  <div
                    key={item.domain}
                    className="rounded-lg border border-current/15 bg-white/70 p-3"
                  >
                    <p className="text-xs font-semibold uppercase opacity-70">
                      {item.label}
                    </p>
                    <p className="mt-2 text-lg font-bold">
                      {item.score}/{item.maximum_score}
                    </p>
                  </div>
                ))}
              </div>

              <div className="mt-5 flex flex-wrap items-center gap-3 text-xs font-semibold">
                <span className="rounded-full border border-current/20 bg-white/70 px-3 py-1.5">
                  Veri tamlığı: %{compatibility.data_completeness_percent}
                </span>
                <span className="rounded-full border border-current/20 bg-white/70 px-3 py-1.5">
                  Hesap türü: Kural tabanlı uyum
                </span>
                <span className="rounded-full border border-current/20 bg-white/70 px-3 py-1.5">
                  Tahmini olasılık: Üretilmiyor
                </span>
              </div>
            </div>

            <div className="mt-5 grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
              <div>
                <h3 className="text-sm font-semibold text-slate-950">
                  Skoru destekleyen bulgular
                </h3>
                {compatibility.supporting_evidence.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {compatibility.supporting_evidence
                      .slice(0, 12)
                      .map((item) => (
                        <span
                          key={item.code}
                          title={item.detail}
                          className="rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1.5 text-xs font-semibold text-cyan-900"
                        >
                          {item.label} · +{item.points}
                        </span>
                      ))}
                  </div>
                ) : (
                  <p className="mt-3 text-sm text-slate-600">
                    Bu hipotezi destekleyen yapılandırılmış bulgu bulunamadı.
                  </p>
                )}
              </div>

              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <h3 className="text-sm font-semibold text-slate-950">
                  Veri kalite kontrolü
                </h3>
                {compatibility.missing_data.length > 0 ? (
                  <ul className="mt-3 space-y-2 text-sm text-slate-700">
                    {compatibility.missing_data.map((item) => (
                      <li key={item}>• Eksik: {item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-3 text-sm text-slate-700">
                    Klinik, laboratuvar ve görüntüleme alanları değerlendirmeye
                    katıldı.
                  </p>
                )}
              </div>
            </div>

            <p className="mt-5 rounded-lg border border-blue-200 bg-blue-50 p-4 text-xs leading-6 text-blue-900">
              {compatibility.disclaimer}
            </p>
          </SectionCard>

          <SectionCard
            title="Birleşik AI klinik değerlendirmesi"
            description="Kan, klinik bilgi ve iki rapor birlikte değerlendirilir."
          >
            <section className="rounded-xl border border-violet-200 bg-violet-50 p-5">
              <p className="whitespace-pre-line text-sm leading-7 text-violet-950">
                {combinedSummary ||
                  'Birleşik klinik değerlendirme için kan analizi ve klinik hasta bilgileri gereklidir.'}
              </p>
              <p className="mt-4 text-xs text-violet-800">
                Bu çıktı karar destek amaçlıdır; tanı veya tedavi kararı değildir.
                Hekim doğrulaması zorunludur.
              </p>
            </section>
          </SectionCard>
        </div>
      ) : null}
    </div>
  );
}
