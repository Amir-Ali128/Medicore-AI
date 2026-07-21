import { useEffect, useMemo, useState, type FormEvent } from 'react';

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
const REVIEW_CACHE_VERSION = 'v3-evidence-checked';

const inFlightReviewRequests = new Map<
  string,
  Promise<ClaudeReviewGenerationResult>
>();

const LAB_ASSERTION_GROUPS = [
  ['potasyum', 'potassium', 'k+'],
  ['sodyum', 'sodium', 'na+'],
  ['klor', 'chloride', 'cl-'],
  ['kalsiyum', 'calcium'],
  ['magnezyum', 'magnesium'],
  ['fosfor', 'phosphorus', 'phosphate'],
  ['glukoz', 'glucose'],
  ['bun', 'üre', 'urea'],
  ['kreatinin', 'creatinine'],
  ['gfr', 'egfr'],
  ['lökosit', 'lokosit', 'wbc', 'leukocyte'],
  ['nötrofil', 'notrofil', 'neutrophil', 'neu'],
  ['lenfosit', 'lymphocyte'],
  ['crp', 'c-reaktif', 'c reaktif'],
  ['sedimentasyon', 'sedim', 'esr'],
  ['prokalsitonin', 'procalcitonin'],
  ['hemoglobin', 'hgb'],
  ['hematokrit', 'hct'],
  ['trombosit', 'platelet', 'plt'],
  ['ast'],
  ['alt'],
  ['alp', 'alkalen fosfataz'],
  ['ggt', 'gama glutamil', 'gamma glutamyl'],
  ['bilirubin'],
  ['amilaz', 'amylase'],
  ['lipaz', 'lipase'],
] as const;

const LAB_DISPLAY_PRIORITIES: Array<[string[], number]> = [
  [['crp', 'c-reaktif', 'c reaktif'], 120],
  [['wbc', 'lökosit', 'lokosit', 'leukocyte'], 115],
  [['nötrofil', 'notrofil', 'neutrophil', 'neu', 'parçalı mutlak', 'parcali mutlak'], 110],
  [['total bilirubin', 'direkt bilirubin', 'bilirubin'], 105],
  [['ggt', 'gama glutamil'], 100],
  [['alp', 'alkalen fosfataz'], 98],
  [['ast'], 92],
  [['alt'], 91],
  [['sedimentasyon', 'sedim', 'esr'], 85],
  [['glukoz', 'glucose'], 70],
  [['bun', 'üre', 'urea'], 60],
  [['kreatinin', 'creatinine'], 59],
  [['gfr', 'egfr'], 58],
];

const REVIEW_STOP_WORDS = new Set([
  'olan',
  'olarak',
  'olabilir',
  'birlikte',
  'degerlendirmesi',
  'gerekir',
  'hasta',
  'klinik',
  'sonuc',
  'bulgu',
  'rapor',
  'duzeyi',
  'yuksekligi',
  'dusuklugu',
]);

function fold(value: string | null | undefined) {
  return (value ?? '')
    .toLocaleLowerCase('tr-TR')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/ı/g, 'i')
    .replace(/\s+/g, ' ')
    .trim();
}

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
  if (sentences.length > 0) return [...new Set(sentences)].slice(0, 6).join(' ');

  const original = report.original_text?.trim() ?? '';
  const resultMatch = original.match(
    /(?:sonuç|sonuc|izlenim)\s*:\s*([\s\S]{1,1200})$/i,
  );
  if (resultMatch?.[1]) {
    return resultMatch[1].replace(/\s+/g, ' ').trim();
  }

  return original
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean)
    .slice(-3)
    .join(' ');
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

function reportFingerprint(report: RadiologyReport) {
  const original = fold(report.original_text).replace(/[^a-z0-9]+/g, ' ').trim();
  if (original) return `${report.modality}:${report.body_part}:${original}`;
  const summary = fold([report.summary, report.impression].filter(Boolean).join(' '));
  return summary || report.id;
}

function sortLatestReports(reports: RadiologyReport[]) {
  const seen = new Set<string>();
  return [...reports]
    .sort((left, right) => {
      const leftDate = Date.parse(left.created_at ?? left.report_date ?? '') || 0;
      const rightDate = Date.parse(right.created_at ?? right.report_date ?? '') || 0;
      return rightDate - leftDate;
    })
    .filter((report) => {
      const key = reportFingerprint(report);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 2);
}

function formatSex(value: string | null | undefined) {
  const normalized = fold(value);
  if (['female', 'kadin', 'woman'].includes(normalized)) return 'Kadın';
  if (['male', 'erkek', 'man'].includes(normalized)) return 'Erkek';
  return value || null;
}

function labHaystack(result: LabAnalysisResult) {
  return fold(
    [result.parameter_code, result.canonical_name, result.raw_parameter_name]
      .filter(Boolean)
      .join(' '),
  );
}

function hasLabAlias(results: LabAnalysisResult[], aliases: readonly string[]) {
  return results.some((result) => {
    const haystack = labHaystack(result);
    return aliases.some((alias) => haystack.includes(fold(alias)));
  });
}

function hasUnsupportedLabAssertion(text: string, results: LabAnalysisResult[]) {
  const normalized = fold(text);
  return LAB_ASSERTION_GROUPS.some(
    (aliases) =>
      aliases.some((alias) => normalized.includes(fold(alias))) &&
      !hasLabAlias(results, aliases),
  );
}

function contextText(
  clinicalContext: ClinicalIntakeInput | null,
  reports: RadiologyReport[],
) {
  return fold(
    [
      clinicalContext?.presenting_complaint.reason_for_visit,
      clinicalContext?.presenting_complaint.chief_complaint,
      clinicalContext?.presenting_complaint.associated_symptoms,
      clinicalContext?.clinical_history_details.history_of_present_illness,
      clinicalContext?.physical_exam.examination_findings,
      ...reports.flatMap((report) => [
        reportSummary(report),
        report.impression,
        report.original_text,
      ]),
    ]
      .filter(Boolean)
      .join(' '),
  );
}

function meaningfulTokens(text: string) {
  return new Set(
    fold(text)
      .replace(/[^a-z0-9çğıöşü]+/g, ' ')
      .split(' ')
      .filter((token) => token.length >= 4 && !REVIEW_STOP_WORDS.has(token)),
  );
}

function reviewSummary(
  review: ClaudeReviewGenerationResult | null,
  labResults: LabAnalysisResult[],
  reports: RadiologyReport[],
  clinicalContext: ClinicalIntakeInput | null,
) {
  if (!review) return { text: '', suppressed: 0 };

  const hypotheses = review.created_hypotheses?.length
    ? review.created_hypotheses
    : review.hypotheses ?? [];
  const contextTokens = meaningfulTokens(contextText(clinicalContext, reports));
  let suppressed = 0;

  const supported = hypotheses
    .filter((item) => {
      const assertion = `${item.title ?? ''} ${item.summary ?? ''}`;
      const unsupported = hasUnsupportedLabAssertion(assertion, labResults);
      if (unsupported) suppressed += 1;
      return !unsupported;
    })
    .map((item, index) => {
      const hypothesisText = `${item.title ?? ''} ${item.summary ?? ''}`;
      const tokens = meaningfulTokens(hypothesisText);
      const overlap = [...tokens].filter((token) => contextTokens.has(token)).length;
      const biliaryBoost = /(kolesistit|safra|koledok|kolestaz|bilirubin|ggt|alp)/.test(
        fold(hypothesisText),
      )
        ? 5
        : 0;
      return { item, index, score: overlap + biliaryBoost };
    })
    .sort((left, right) => right.score - left.score || left.index - right.index)
    .slice(0, 5)
    .map(({ item }) => {
      const title = item.title?.trim();
      const summary = item.summary?.trim();
      if (title && summary && !fold(summary).startsWith(fold(title))) {
        return `${title}: ${summary}`;
      }
      return summary || title || '';
    })
    .filter(Boolean);

  return {
    text: [...new Set(supported)].join('\n\n'),
    suppressed,
  };
}

function reviewScope(analysisRunId: string, latestReportId: string | null) {
  return `${REVIEW_CACHE_VERSION}:${analysisRunId}:${latestReportId ?? 'no-radiology-report'}`;
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

  const request = evaluateClaudeAbnormalResults(analysisRunId, 6, context)
    .then((review) => rememberReview(scope, review))
    .finally(() => {
      inFlightReviewRequests.delete(scope);
    });

  inFlightReviewRequests.set(scope, request);
  return request;
}

function labDisplayPriority(result: LabAnalysisResult) {
  const haystack = labHaystack(result);
  const configured = LAB_DISPLAY_PRIORITIES.find(([aliases]) =>
    aliases.some((alias) => haystack.includes(fold(alias))),
  );
  const statusBoost = ['high', 'low'].includes(result.result_status) ? 10 : 0;
  return (configured?.[1] ?? 0) + statusBoost;
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
        {reportSummary(report) || 'Rapor metninden güvenilir özet çıkarılamadı.'}
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

        const latestReports = sortLatestReports(allReports);
        setReports(latestReports);
        setResult(latestReports[0] ?? null);
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

        setStatus('Klinik, laboratuvar ve görüntüleme verileri yüklendi; AI değerlendirmesi hazırlanıyor…');
        try {
          const review = await loadOrCreateReview(
            analysisRunId,
            latestReports[0]?.id ?? null,
            context,
          );
          if (!cancelled) setCombinedReview(review);
        } catch (reviewError) {
          if (!cancelled) {
            setError(
              reviewError instanceof Error
                ? reviewError.message
                : 'AI klinik değerlendirmesi oluşturulamadı.',
            );
          }
        }

        if (!cancelled) {
          setStatus('Kayıtlı kan sonuçları, klinik hasta bilgileri ve benzersiz görüntüleme raporları birlikte yüklendi.');
        }
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

      const context = readClinicalContext();
      setClinicalContext(context);

      const allReports = await listPatientRadiologyReports();
      const latestReports = sortLatestReports([report, ...allReports]);
      setReports(latestReports);
      setResult(latestReports[0] ?? report);

      const analysisRunId = localStorage.getItem(LAST_ANALYSIS_RUN_ID_KEY);
      if (!analysisRunId) {
        setLabResults([]);
        setStatus('Rapor kaydedildi. Kan sonuçları eklenince birleşik değerlendirme oluşturulabilir.');
        return;
      }

      const latestLabResults = await getAnalysisRunResults(analysisRunId);
      setLabResults(latestLabResults);

      if (!context || latestLabResults.length === 0) {
        setStatus('Rapor kaydedildi; birleşik AI değerlendirmesi için klinik bağlam ve yapılandırılmış kan sonuçları gerekli.');
        return;
      }

      const latestReportId = latestReports[0]?.id ?? report.id;
      const scope = reviewScope(analysisRunId, latestReportId);
      const review = rememberReview(
        scope,
        await evaluateClaudeAbnormalResults(analysisRunId, 6, context),
      );

      setCombinedReview(review);
      setStatus('Kan sonuçları, klinik hasta bilgileri ve benzersiz görüntüleme raporları birlikte değerlendirildi.');
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
  const patient = clinicalContext?.patient_information;
  const complaint = clinicalContext?.presenting_complaint;
  const history = clinicalContext?.clinical_history_details;
  const displayedLabResults = useMemo(() => {
    const abnormal = labResults.filter((item) =>
      ['high', 'low', 'needs_review'].includes(item.result_status),
    );
    return [...(abnormal.length > 0 ? abnormal : labResults)]
      .sort((left, right) => labDisplayPriority(right) - labDisplayPriority(left))
      .slice(0, 12);
  }, [labResults]);
  const review = useMemo(
    () => reviewSummary(combinedReview, labResults, reports, clinicalContext),
    [combinedReview, labResults, reports, clinicalContext],
  );
  const compatibility = useMemo(
    () =>
      calculateAcuteCholecystitisCompatibility({
        clinicalContext,
        labResults,
        reports: reports.length > 0 ? reports : result ? [result] : [],
      }),
    [clinicalContext, labResults, reports, result],
  );
  const urgencyClass =
    urgency === 'ACİL'
      ? 'border-red-300 bg-red-600 text-white'
      : urgency === 'DİKKAT'
        ? 'border-amber-300 bg-amber-100 text-amber-950'
        : 'border-emerald-300 bg-emerald-100 text-emerald-950';
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
        <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">Raporlama</p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">Birleşik hasta değerlendirmesi</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Kan sonuçlarını, klinik hasta bilgilerini ve benzersiz görüntüleme raporlarını aynı sayfada değerlendirir.
        </p>
      </header>

      <form onSubmit={submit}>
        <SectionCard title="Yeni görüntüleme raporu" description="Metni yapıştır veya PDF yükle.">
          <div className="flex gap-2">
            <button type="button" onClick={() => setMode('manual')} className="rounded-lg border px-4 py-2 text-sm font-semibold">
              Rapor metni
            </button>
            <button type="button" onClick={() => setMode('pdf')} className="rounded-lg border px-4 py-2 text-sm font-semibold">
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

          {status ? <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">{status}</p> : null}
          {error ? <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">{error}</p> : null}

          <button type="submit" disabled={busy} className="mt-5 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-60">
            {busy ? 'Tüm veriler değerlendiriliyor…' : 'Kaydet ve tüm verilerle değerlendir'}
          </button>
        </SectionCard>
      </form>

      {result ? (
        <div className="space-y-6">
          <SectionCard title="Yeni raporun özeti" description={`${result.modality} · ${result.body_part}`}>
            <div className="space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className={`rounded-full border px-4 py-2 text-sm font-extrabold tracking-wide ${urgencyClass}`}>
                  Klinik öncelik: {urgency}
                </span>
                <span className="text-xs text-slate-500">Hekim doğrulaması zorunludur.</span>
              </div>
              <section className="rounded-xl border border-blue-200 bg-blue-50 p-5">
                <h2 className="font-semibold text-blue-950">AI radyoloji özeti</h2>
                <p className="mt-3 text-sm leading-7 text-blue-950">{summary || 'Bu rapor için özet oluşturulamadı.'}</p>
              </section>
            </div>
          </SectionCard>

          <div className="grid gap-6 xl:grid-cols-2">
            <SectionCard title="Klinik hasta bilgileri" description="Aktif hasta kaydından alınır.">
              {patient || complaint || history ? (
                <div className="space-y-4 text-sm text-slate-700">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <p><span className="font-semibold text-slate-950">Hasta:</span> {patient?.full_name || 'Belirtilmedi'}</p>
                    <p><span className="font-semibold text-slate-950">Yaş / cinsiyet:</span> {[patient?.age, formatSex(patient?.sex)].filter(Boolean).join(' / ') || 'Belirtilmedi'}</p>
                  </div>
                  <p><span className="font-semibold text-slate-950">Başvuru nedeni:</span> {complaint?.reason_for_visit || complaint?.chief_complaint || 'Belirtilmedi'}</p>
                  <p><span className="font-semibold text-slate-950">Semptomlar:</span> {complaint?.associated_symptoms || 'Belirtilmedi'}</p>
                  <p><span className="font-semibold text-slate-950">Klinik öykü:</span> {history?.history_of_present_illness || history?.current_medical_conditions || 'Belirtilmedi'}</p>
                </div>
              ) : (
                <p className="text-sm text-slate-600">Aktif klinik hasta bilgisi bulunamadı.</p>
              )}
            </SectionCard>

            <SectionCard title="Kan sonuçları" description="Vakayla en ilişkili anormal sonuçlar önce gösterilir.">
              {displayedLabResults.length > 0 ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  {displayedLabResults.map((item) => <LabResultCard key={item.lab_result_id} result={item} />)}
                </div>
              ) : (
                <p className="text-sm text-slate-600">Bu hasta için analiz edilmiş kan sonucu bulunamadı.</p>
              )}
            </SectionCard>
          </div>

          <SectionCard title="Benzersiz görüntüleme raporları" description="Aynı içerikli mükerrer kayıtlar tek rapor olarak gösterilir.">
            {reports.length > 0 ? (
              <div className="grid gap-4 lg:grid-cols-2">
                {reports.map((report, index) => <ReportCard key={report.id} report={report} index={index} />)}
              </div>
            ) : (
              <p className="text-sm text-slate-600">Görüntüleme raporu bulunamadı.</p>
            )}
          </SectionCard>

          <SectionCard title="Klinik uyum skoru" description="Tanı olasılığı değil; yapılandırılmış bulguların belirli bir klinik hipotezle deterministik uyumudur.">
            <div className={`rounded-xl border p-5 ${compatibilityClass}`}>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-xs font-extrabold uppercase tracking-wide">Değerlendirilen hipotez</p>
                  <h2 className="mt-2 text-xl font-semibold">{compatibility.display_name}</h2>
                  <p className="mt-2 text-sm font-semibold">{compatibility.level_label}</p>
                </div>
                <div className="rounded-xl border border-current/20 bg-white/70 px-6 py-4 text-center">
                  <p className="text-4xl font-black">{compatibility.score}</p>
                  <p className="mt-1 text-sm font-semibold">/ {compatibility.maximum_score}</p>
                </div>
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {compatibility.breakdown.map((item) => (
                  <div key={item.domain} className="rounded-lg border border-current/15 bg-white/70 p-3">
                    <p className="text-xs font-semibold uppercase opacity-70">{item.label}</p>
                    <p className="mt-2 text-lg font-bold">{item.score}/{item.maximum_score}</p>
                  </div>
                ))}
              </div>

              <div className="mt-5 flex flex-wrap items-center gap-3 text-xs font-semibold">
                <span className="rounded-full border border-current/20 bg-white/70 px-3 py-1.5">Veri tamlığı: %{compatibility.data_completeness_percent}</span>
                <span className="rounded-full border border-current/20 bg-white/70 px-3 py-1.5">Hesap türü: Kural tabanlı uyum</span>
                <span className="rounded-full border border-current/20 bg-white/70 px-3 py-1.5">Tahmini olasılık: Üretilmiyor</span>
              </div>
            </div>

            <div className="mt-5 grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
              <div>
                <h3 className="text-sm font-semibold text-slate-950">Skoru destekleyen bulgular</h3>
                {compatibility.supporting_evidence.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {compatibility.supporting_evidence.slice(0, 16).map((item) => (
                      <span key={item.code} title={item.detail} className="rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1.5 text-xs font-semibold text-cyan-900">
                        {item.label} · +{item.points}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-sm text-slate-600">Bu hipotezi destekleyen yapılandırılmış bulgu bulunamadı.</p>
                )}
              </div>

              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <h3 className="text-sm font-semibold text-slate-950">Veri kalite kontrolü</h3>
                {compatibility.missing_data.length > 0 ? (
                  <ul className="mt-3 space-y-2 text-sm text-slate-700">
                    {compatibility.missing_data.map((item) => <li key={item}>• Eksik: {item}</li>)}
                  </ul>
                ) : (
                  <p className="mt-3 text-sm text-slate-700">Klinik, laboratuvar ve görüntüleme alanları değerlendirmeye katıldı.</p>
                )}
              </div>
            </div>

            <p className="mt-5 rounded-lg border border-blue-200 bg-blue-50 p-4 text-xs leading-6 text-blue-900">{compatibility.disclaimer}</p>
          </SectionCard>

          <SectionCard title="Birleşik AI klinik değerlendirmesi" description="Kan, klinik bilgi ve benzersiz raporlar birlikte değerlendirilir.">
            <section className="rounded-xl border border-violet-200 bg-violet-50 p-5">
              <p className="whitespace-pre-line text-sm leading-7 text-violet-950">
                {review.text || 'Birleşik klinik değerlendirme için desteklenen AI özeti oluşturulamadı.'}
              </p>
              {review.suppressed > 0 ? (
                <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">
                  Mevcut kan sonuçlarında karşılığı bulunmayan {review.suppressed} AI ifadesi güvenlik filtresiyle gösterilmedi.
                </p>
              ) : null}
              <p className="mt-4 text-xs text-violet-800">Bu çıktı karar destek amaçlıdır; tanı veya tedavi kararı değildir. Hekim doğrulaması zorunludur.</p>
            </section>
          </SectionCard>
        </div>
      ) : null}
    </div>
  );
}
