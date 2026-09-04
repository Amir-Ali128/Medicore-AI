import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import ClaudeEvaluationCard from '../components/clinical/ClaudeEvaluationCard';
import { clearAccessToken } from '../services/authClient';
import {
  evaluateClinicalBrain,
  type ClinicalBrainResult,
} from '../services/clinicalBrainClient';
import type {
  ClaudeEvaluationHypothesis,
  ClaudeReviewGenerationResult,
} from '../services/claudeReviewClient';
import { deleteCompactEvaluation } from '../services/evaluationDeleteClient';
import {
  getClinicalHypothesesForAnalysisRun,
  type ClinicalHypothesis,
} from '../services/clinicalHypothesesClient';
import {
  getAnalysisRunResults,
  LAST_ANALYSIS_RUN_ID_KEY,
  type ClinicalIntakeInput,
} from '../services/labAnalysisClient';
import {
  evaluateMultisourceCase,
  type CaseSourceAvailability,
} from '../services/multisourceEvaluationClient';
import {
  ACTIVE_PATIENT_ID_KEY,
  listPatientRadiologyReports,
  type RadiologyReport,
} from '../services/radiologyClient';
import {
  deleteSourceOnlyEvaluationsForPatient,
  getSourceOnlyEvaluationsForPatient,
} from '../services/sourceOnlyEvaluationClient';

const ACTIVE_CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';
const CASE_SUMMARY_UPDATED_EVENT = 'medicore:case-summary-updated';

function readClinicalIntake(): ClinicalIntakeInput | null {
  try {
    const raw = localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY);
    return raw ? (JSON.parse(raw) as ClinicalIntakeInput) : null;
  } catch {
    return null;
  }
}

function errorMessage(value: unknown): string {
  return value instanceof Error ? value.message : String(value ?? '');
}

function isAuthSessionError(value: unknown): boolean {
  const message = errorMessage(value).toLowerCase();
  return (
    message.includes('401') &&
    (message.includes('auth token') ||
      message.includes('expired') ||
      message.includes('unauthorized') ||
      message.includes('user not found'))
  );
}

function isCompactEvaluation(
  hypothesis: ClinicalHypothesis | ClaudeEvaluationHypothesis,
) {
  return (
    hypothesis.hypothesis_type === 'compact_risk_summary' ||
    hypothesis.metadata_json?.compact_mode === true
  );
}

function keepOnlyNewestCompactEvaluation(
  hypotheses: Array<ClinicalHypothesis | ClaudeEvaluationHypothesis>,
) {
  let compactSeen = false;

  return hypotheses.filter((hypothesis) => {
    if (!isCompactEvaluation(hypothesis)) return true;
    if (compactSeen) return false;
    compactSeen = true;
    return true;
  });
}

function coverageLabel(count: number) {
  if (count >= 3) return 'Tam kaynak kapsamı';
  if (count === 2) return 'Kısmi kaynak kapsamı';
  if (count === 1) return 'Sınırlı kaynak kapsamı';
  return 'Kaynak yok';
}

function SourceStatus({
  title,
  ready,
  link,
}: {
  title: string;
  ready: boolean;
  link: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="font-semibold text-slate-900">{title}</p>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
            ready
              ? 'bg-emerald-100 text-emerald-800'
              : 'bg-amber-100 text-amber-800'
          }`}
        >
          {ready ? 'Hazır' : 'Eksik'}
        </span>
      </div>
      {!ready ? (
        <Link
          to={link}
          className="mt-3 inline-flex text-sm font-semibold text-blue-700 hover:text-blue-800"
        >
          Ekle →
        </Link>
      ) : null}
    </div>
  );
}

function SummaryCard({
  title,
  text,
  date,
}: {
  title: string;
  text: string;
  date?: string | null;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
          {title}
        </p>
        {date ? (
          <span className="rounded-full bg-white px-2 py-1 text-[11px] font-semibold text-slate-500 ring-1 ring-slate-200">
            {date}
          </span>
        ) : null}
      </div>
      <p className="mt-2 text-sm leading-6 text-slate-700">{text}</p>
    </div>
  );
}

export default function CaseEvaluationPage() {
  const navigate = useNavigate();
  const [clinicalIntake, setClinicalIntake] = useState<ClinicalIntakeInput | null>(null);
  const [radiologyReports, setRadiologyReports] = useState<RadiologyReport[]>([]);
  const [brain, setBrain] = useState<ClinicalBrainResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [result, setResult] = useState<ClaudeReviewGenerationResult | null>(null);
  const [storedHypotheses, setStoredHypotheses] = useState<ClinicalHypothesis[]>([]);
  const [error, setError] = useState('');

  const analysisRunId = localStorage.getItem(LAST_ANALYSIS_RUN_ID_KEY);
  const activePatientId = localStorage.getItem(ACTIVE_PATIENT_ID_KEY);

  useEffect(() => {
    let cancelled = false;

    async function loadSources() {
      setLoading(true);
      setError('');
      setBrain(null);

      const intake = readClinicalIntake();
      if (!cancelled) setClinicalIntake(intake);

      const [labsResult, reportsResult] = await Promise.allSettled([
        analysisRunId
          ? getAnalysisRunResults(analysisRunId)
          : Promise.resolve([]),
        listPatientRadiologyReports(null, { includeUnanalyzed: true }),
      ]);

      if (cancelled) return;

      const labs = labsResult.status === 'fulfilled' ? labsResult.value : [];
      const reports = reportsResult.status === 'fulfilled' ? reportsResult.value : [];
      setRadiologyReports(reports);

      let brainResult: ClinicalBrainResult | null = null;
      let brainFailure: unknown = null;
      try {
        brainResult = await evaluateClinicalBrain({
          clinical_context: intake,
          lab_results: labs,
          radiology_reports: reports,
          language: 'tr',
        });
      } catch (brainError) {
        brainFailure = brainError;
      }
      if (cancelled) return;
      setBrain(brainResult);

      const selectedUltrasound = brainResult?.selected_ultrasound_report_id
        ? reports.find(
            (report) => report.id === brainResult?.selected_ultrasound_report_id,
          ) ?? null
        : null;
      const patientId =
        activePatientId ?? selectedUltrasound?.patient_id ?? reports[0]?.patient_id ?? null;

      let hypotheses: ClinicalHypothesis[] = [];
      let hypothesisFailure: unknown = null;
      try {
        if (
          analysisRunId &&
          brainResult?.source_availability.laboratory === true
        ) {
          hypotheses = await getClinicalHypothesesForAnalysisRun(analysisRunId);
        } else if (patientId) {
          hypotheses = await getSourceOnlyEvaluationsForPatient(patientId);
        }
      } catch (loadError) {
        hypothesisFailure = loadError;
      }
      if (cancelled) return;
      setStoredHypotheses(hypotheses);

      const failures = [labsResult, reportsResult]
        .filter(
          (entry): entry is PromiseRejectedResult => entry.status === 'rejected',
        )
        .map((entry) => entry.reason);
      if (brainFailure) failures.push(brainFailure);
      if (hypothesisFailure) failures.push(hypothesisFailure);

      if (failures.some(isAuthSessionError)) {
        clearAccessToken();
        navigate('/login', { replace: true });
        return;
      }

      const hasAnyReadySource = brainResult
        ? Object.values(brainResult.source_availability).some(Boolean)
        : false;
      if (failures.length > 0 && !hasAnyReadySource) {
        setError(
          brainFailure
            ? 'Klinik Brain hazırlanamadı. Tarayıcı yerel klinik karar mantığına geri dönmedi; lütfen tekrar dene.'
            : errorMessage(failures[0]) || 'Kayıtlı bilgiler yüklenemedi.',
        );
      }

      setLoading(false);
    }

    void loadSources();
    return () => {
      cancelled = true;
    };
  }, [activePatientId, analysisRunId, navigate]);

  const latestUltrasound = useMemo(
    () =>
      brain?.selected_ultrasound_report_id
        ? radiologyReports.find(
            (report) => report.id === brain.selected_ultrasound_report_id,
          ) ?? null
        : null,
    [brain?.selected_ultrasound_report_id, radiologyReports],
  );

  const sourceAvailability = useMemo<CaseSourceAvailability>(
    () =>
      brain?.source_availability ?? {
        clinical: false,
        laboratory: false,
        ultrasound: false,
      },
    [brain?.source_availability],
  );
  const clinicalReady = sourceAvailability.clinical;
  const labReady = sourceAvailability.laboratory;
  const ultrasoundReady = sourceAvailability.ultrasound;
  const availableSourceCount = useMemo(
    () => Object.values(sourceAvailability).filter(Boolean).length,
    [sourceAvailability],
  );
  const patientId =
    activePatientId ?? latestUltrasound?.patient_id ?? radiologyReports[0]?.patient_id ?? null;
  const evaluationAnalysisRunId = labReady ? analysisRunId : null;
  const canEvaluate =
    Boolean(brain) &&
    availableSourceCount > 0 &&
    Boolean(evaluationAnalysisRunId || patientId);

  const sourceDates = brain?.source_dates ?? {
    laboratory: null,
    ultrasound: null,
  };
  const sourceGapDays = brain?.temporal_gap_days ?? null;
  const performedStudies = brain?.performed_studies ?? [];
  const sourceSummaries = brain?.source_summaries ?? {
    clinical: 'Python Clinical Brain bekleniyor.',
    laboratory: 'Python Clinical Brain bekleniyor.',
    ultrasound: 'Python Clinical Brain bekleniyor.',
  };

  const findings = useMemo<
    Array<ClinicalHypothesis | ClaudeEvaluationHypothesis>
  >(() => {
    const hypotheses = result
      ? result.created_hypotheses?.length
        ? result.created_hypotheses
        : result.hypotheses ?? []
      : storedHypotheses;

    return keepOnlyNewestCompactEvaluation(hypotheses);
  }, [result, storedHypotheses]);

  async function handleEvaluate() {
    if (!canEvaluate || !brain) return;

    try {
      setEvaluating(true);
      setError('');
      setResult(null);

      const nextResult = await evaluateMultisourceCase(
        evaluationAnalysisRunId,
        patientId,
        clinicalIntake,
        brain.ai_source_summaries,
        sourceAvailability.ultrasound ? brain.ultrasound_context_flags : [],
        {
          performedStudies,
          sourceDates,
          sourceAvailability,
        },
      );
      setResult(nextResult);
      setStoredHypotheses(
        (nextResult.created_hypotheses ??
          nextResult.hypotheses ??
          []) as ClinicalHypothesis[],
      );
      window.dispatchEvent(new Event(CASE_SUMMARY_UPDATED_EVENT));
    } catch (evaluationError) {
      if (isAuthSessionError(evaluationError)) {
        clearAccessToken();
        navigate('/login', { replace: true });
        return;
      }

      setError(
        evaluationError instanceof Error
          ? evaluationError.message
          : 'Değerlendirme oluşturulamadı.',
      );
    } finally {
      setEvaluating(false);
    }
  }

  async function handleDeleteEvaluation() {
    if (deleting || (!evaluationAnalysisRunId && !patientId)) return;
    if (!window.confirm('AI tarafından oluşturulan değerlendirme silinsin mi?')) return;

    try {
      setDeleting(true);
      setError('');
      if (evaluationAnalysisRunId) {
        await deleteCompactEvaluation(evaluationAnalysisRunId);
      } else if (patientId) {
        await deleteSourceOnlyEvaluationsForPatient(patientId);
      }
      setResult(null);
      setStoredHypotheses((current) =>
        current.filter((hypothesis) => !isCompactEvaluation(hypothesis)),
      );
      window.dispatchEvent(new Event(CASE_SUMMARY_UPDATED_EVENT));
    } catch (deleteError) {
      setError(errorMessage(deleteError) || 'AI değerlendirmesi silinemedi.');
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <header>
        <h1 className="text-2xl font-bold text-slate-950">Bulguları Değerlendir</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          Mevcut klinik, laboratuvar ve ultrason kaynakları Python Clinical Brain
          tarafından tek kuralla hazırlanır; eksik kaynaklar varsayılmaz.
        </p>
      </header>

      <div className="grid gap-3 md:grid-cols-3">
        <SourceStatus title="Hasta bilgileri" ready={clinicalReady} link="/patients/demo" />
        <SourceStatus title="Laboratuvar" ready={labReady} link="/analysis/mock" />
        <SourceStatus title="Ultrason" ready={ultrasoundReady} link="/radiology" />
      </div>

      <div
        className={`rounded-xl border px-4 py-3 text-sm ${
          availableSourceCount === 3
            ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
            : availableSourceCount > 0
              ? 'border-amber-200 bg-amber-50 text-amber-900'
              : 'border-slate-200 bg-slate-50 text-slate-600'
        }`}
      >
        <span className="font-semibold">
          Kaynak kapsamı: {availableSourceCount}/3 · {coverageLabel(availableSourceCount)}
        </span>
        {availableSourceCount > 0 && availableSourceCount < 3 ? (
          <span> — değerlendirme yalnızca hazır kaynaklarla sınırlandırılır.</span>
        ) : null}
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div>
          <h2 className="text-lg font-bold text-slate-950">Vaka Özeti</h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            Özet, kaynak seçimi ve zaman uyumu backend Python tarafından hazırlanır.
            Normal laboratuvar sonuçları kompakt AI özetine dahil edilmez.
          </p>
        </div>

        {sourceGapDays != null && sourceGapDays > 90 ? (
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">
            <span className="font-semibold">Zamansal uyumsuzluk:</span>{' '}
            laboratuvar ve ultrason kaynakları arasında {sourceGapDays} gün var.
            Birlikte yorumlanırken eşzamanlı veri kabul edilmemelidir.
          </div>
        ) : null}

        <div className="mt-4 grid gap-3">
          <SummaryCard title="Klinik özet" text={sourceSummaries.clinical} />
          <SummaryCard
            title="Laboratuvar özeti · yalnızca yüksek/düşük"
            text={sourceSummaries.laboratory}
            date={sourceDates.laboratory}
          />
          <SummaryCard
            title="Ultrason sonucu"
            text={sourceSummaries.ultrasound}
            date={sourceDates.ultrasound}
          />
        </div>
      </section>

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      <button
        type="button"
        onClick={handleEvaluate}
        disabled={!canEvaluate || loading || evaluating}
        className="w-full rounded-xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
      >
        {loading
          ? 'Kontrol ediliyor...'
          : evaluating
            ? 'Değerlendiriliyor...'
            : 'Gerekirse AI ile değerlendir'}
      </button>

      {!loading && availableSourceCount === 0 ? (
        <p className="text-sm text-slate-500">
          Değerlendirme için en az bir kaynak ekle.
        </p>
      ) : null}

      {!loading && availableSourceCount > 0 && !canEvaluate ? (
        <p className="text-sm text-amber-700">
          Tek veya kısmi kaynakla değerlendirme için önce hasta kaydını kaydet.
        </p>
      ) : null}

      {!loading && canEvaluate && availableSourceCount < 3 ? (
        <p className="text-sm text-amber-700">
          Sınırlı kaynak kapsamıyla değerlendirme yapılacak; eksik kaynaklar
          varsayılmayacak ve sonuç hekim doğrulaması gerektirecek.
        </p>
      ) : null}

      {result || storedHypotheses.length > 0 ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold text-slate-950">AI Değerlendirmesi</h2>
              <p className="mt-1 text-xs text-slate-500">
                {availableSourceCount}/3 kaynak · {coverageLabel(availableSourceCount)}
              </p>
            </div>
            {findings.some(isCompactEvaluation) ? (
              <button
                type="button"
                onClick={() => void handleDeleteEvaluation()}
                disabled={deleting}
                className="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-700 transition hover:bg-red-50 disabled:opacity-50"
              >
                {deleting ? 'Siliniyor...' : 'AI çıktısını sil'}
              </button>
            ) : null}
          </div>

          {findings.length > 0 ? (
            <div className="mt-4 space-y-4">
              {findings.map((finding) =>
                isCompactEvaluation(finding) ? (
                  <ClaudeEvaluationCard
                    key={finding.id}
                    hypothesis={finding as ClaudeEvaluationHypothesis}
                  />
                ) : (
                  <div key={finding.id} className="rounded-xl bg-slate-50 p-4">
                    <p className="font-semibold text-slate-900">{finding.title}</p>
                    <p className="mt-1 text-sm leading-6 text-slate-600">
                      {finding.summary}
                    </p>
                  </div>
                ),
              )}
            </div>
          ) : (
            <p className="mt-4 text-sm leading-6 text-slate-600">
              Hazır kaynaklarda deterministik değerlendirme gerektiren bir bulgu
              oluşmadıysa yeni AI çıktısı oluşturulmayabilir.
            </p>
          )}

          {result && result.warnings.length > 0 ? (
            <p className="mt-4 text-xs leading-5 text-slate-500">
              {result.warnings.join(' ')}
            </p>
          ) : null}

          <p className="mt-5 border-t border-slate-100 pt-4 text-xs leading-5 text-slate-500">
            Bu çıktı klinik karar desteği içindir; kesin tanı veya tedavi kararı
            değildir ve hekim değerlendirmesi gerektirir. Eksik kaynaklar mevcutmuş
            gibi varsayılmaz.
          </p>
        </section>
      ) : null}
    </div>
  );
}
