import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import ClaudeEvaluationCard from '../components/clinical/ClaudeEvaluationCard';
import type {
  ClaudeEvaluationHypothesis,
  ClaudeReviewGenerationResult,
} from '../services/claudeReviewClient';
import { clearAccessToken } from '../services/authClient';
import {
  buildClinicalAiSummary,
  buildClinicalSummary,
  buildLaboratoryAiSummary,
  buildLaboratorySummary,
  buildPerformedStudyInventory,
  buildUltrasoundContextFlags,
  buildUltrasoundSummary,
  getLatestUltrasoundReport,
  type CaseSourceSummaries,
} from '../services/caseEvaluationSummary';
import { deleteCompactEvaluation } from '../services/evaluationDeleteClient';
import {
  getAnalysisRunResults,
  LAST_ANALYSIS_RUN_ID_KEY,
  type ClinicalIntakeInput,
  type LabAnalysisResult,
} from '../services/labAnalysisClient';
import { evaluateMultisourceCase } from '../services/multisourceEvaluationClient';
import { buildRadiologyComparisonSummary } from '../services/radiologyCaseContext';
import {
  listPatientRadiologyReports,
  type RadiologyReport,
} from '../services/radiologyClient';
import {
  getClinicalHypothesesForAnalysisRun,
  type ClinicalHypothesis,
} from '../services/clinicalHypothesesClient';

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

function hasMeaningfulValue(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === 'string') return Boolean(value.trim());
  if (typeof value === 'number') return Number.isFinite(value);
  if (typeof value === 'boolean') return value;
  if (Array.isArray(value)) return value.some(hasMeaningfulValue);
  if (typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).some(hasMeaningfulValue);
  }
  return false;
}

function hasClinicalData(value: ClinicalIntakeInput | null) {
  return hasMeaningfulValue(value);
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

function SummaryCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <p className="text-xs font-bold uppercase tracking-wide text-slate-500">{title}</p>
      <p className="mt-2 text-sm leading-6 text-slate-700">{text}</p>
    </div>
  );
}

export default function CaseEvaluationPage() {
  const navigate = useNavigate();
  const [clinicalIntake, setClinicalIntake] = useState<ClinicalIntakeInput | null>(null);
  const [labResults, setLabResults] = useState<LabAnalysisResult[]>([]);
  const [radiologyReports, setRadiologyReports] = useState<RadiologyReport[]>([]);
  const [labReady, setLabReady] = useState(false);
  const [ultrasoundReady, setUltrasoundReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [result, setResult] = useState<ClaudeReviewGenerationResult | null>(null);
  const [storedHypotheses, setStoredHypotheses] = useState<ClinicalHypothesis[]>([]);
  const [error, setError] = useState('');

  const analysisRunId = localStorage.getItem(LAST_ANALYSIS_RUN_ID_KEY);
  const clinicalReady = hasClinicalData(clinicalIntake);
  const allReady = clinicalReady && labReady && ultrasoundReady;

  useEffect(() => {
    let cancelled = false;

    async function loadSources() {
      setLoading(true);
      setError('');

      const intake = readClinicalIntake();
      if (!cancelled) setClinicalIntake(intake);

      const [labsResult, reportsResult, hypothesesResult] =
        await Promise.allSettled([
          analysisRunId
            ? getAnalysisRunResults(analysisRunId)
            : Promise.resolve([]),
          listPatientRadiologyReports(null, { includeUnanalyzed: true }),
          analysisRunId
            ? getClinicalHypothesesForAnalysisRun(analysisRunId)
            : Promise.resolve([]),
        ]);

      if (cancelled) return;

      const labs = labsResult.status === 'fulfilled' ? labsResult.value : [];
      const reports = reportsResult.status === 'fulfilled' ? reportsResult.value : [];
      setLabResults(labs);
      setRadiologyReports(reports);
      setLabReady(labs.length > 0);
      setUltrasoundReady(Boolean(getLatestUltrasoundReport(reports)));
      setStoredHypotheses(
        hypothesesResult.status === 'fulfilled' ? hypothesesResult.value : [],
      );

      const failures = [labsResult, reportsResult, hypothesesResult]
        .filter(
          (entry): entry is PromiseRejectedResult => entry.status === 'rejected',
        )
        .map((entry) => entry.reason);

      if (failures.some(isAuthSessionError)) {
        clearAccessToken();
        navigate('/login', { replace: true });
        return;
      }

      if (failures.length > 0) {
        setError(errorMessage(failures[0]) || 'Kayıtlı bilgiler yüklenemedi.');
      }

      setLoading(false);
    }

    void loadSources();
    return () => {
      cancelled = true;
    };
  }, [analysisRunId, navigate]);

  const latestUltrasound = useMemo(
    () => getLatestUltrasoundReport(radiologyReports),
    [radiologyReports],
  );

  const performedStudies = useMemo(
    () => buildPerformedStudyInventory(radiologyReports),
    [radiologyReports],
  );

  const radiologyComparison = useMemo(
    () => buildRadiologyComparisonSummary(radiologyReports),
    [radiologyReports],
  );

  const sourceSummaries = useMemo<CaseSourceSummaries>(
    () => ({
      clinical: buildClinicalSummary(clinicalIntake),
      laboratory: buildLaboratorySummary(labResults),
      ultrasound: buildUltrasoundSummary(latestUltrasound),
      performed_studies: performedStudies,
    }),
    [clinicalIntake, labResults, latestUltrasound, performedStudies],
  );

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
    if (!analysisRunId || !clinicalIntake || !allReady) return;

    try {
      setEvaluating(true);
      setError('');
      setResult(null);

      const aiSummaries: CaseSourceSummaries = {
        clinical: buildClinicalAiSummary(clinicalIntake),
        laboratory: buildLaboratoryAiSummary(labResults),
        ultrasound: sourceSummaries.ultrasound,
        performed_studies: performedStudies,
      };
      const nextResult = await evaluateMultisourceCase(
        analysisRunId,
        clinicalIntake,
        aiSummaries,
        buildUltrasoundContextFlags(latestUltrasound),
        radiologyComparison,
      );
      setResult(nextResult);
      setStoredHypotheses(
        (nextResult.created_hypotheses ?? nextResult.hypotheses ?? []) as ClinicalHypothesis[],
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
    if (!analysisRunId || deleting) return;
    if (!window.confirm('AI tarafından oluşturulan değerlendirme silinsin mi?')) return;

    try {
      setDeleting(true);
      setError('');
      await deleteCompactEvaluation(analysisRunId);
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
          Önce klinik, yüksek/düşük laboratuvar bulguları ve ultrason sonucu kısa bir vaka özetine dönüştürülür; yalnızca gerekirse kompakt AI değerlendirmesi çalışır.
        </p>
      </header>

      <div className="grid gap-3 md:grid-cols-3">
        <SourceStatus title="Hasta bilgileri" ready={clinicalReady} link="/patients/demo" />
        <SourceStatus title="Laboratuvar" ready={labReady} link="/analysis/mock" />
        <SourceStatus title="Ultrason" ready={ultrasoundReady} link="/radiology" />
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div>
          <h2 className="text-lg font-bold text-slate-950">Vaka Özeti</h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            Kaynak tarihleri korunur. Tam dosya AI'ya gönderilmez; normal laboratuvar sonuçları bu özete dahil edilmez.
          </p>
        </div>
        <div className="mt-4 grid gap-3">
          <SummaryCard title="Klinik özet" text={sourceSummaries.clinical} />
          <SummaryCard title="Laboratuvar özeti · yalnızca yüksek/düşük" text={sourceSummaries.laboratory} />
          <SummaryCard title="Ultrason sonucu" text={sourceSummaries.ultrasound} />
          {radiologyComparison ? (
            <SummaryCard title="Radyoloji karşılaştırması" text={radiologyComparison} />
          ) : null}
        </div>
        {performedStudies.length > 0 ? (
          <p className="mt-3 text-xs leading-5 text-slate-500">
            {performedStudies.length} kanonik görüntüleme/tetkik kaydı mevcut; tekrar öneriler otomatik filtrelenir.
          </p>
        ) : null}
      </section>

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      <button
        type="button"
        onClick={handleEvaluate}
        disabled={!allReady || loading || evaluating}
        className="w-full rounded-xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
      >
        {loading ? 'Kontrol ediliyor...' : evaluating ? 'Değerlendiriliyor...' : 'Gerekirse AI ile değerlendir'}
      </button>

      {!loading && !allReady ? (
        <p className="text-sm text-slate-500">
          Değerlendirme için klinik, laboratuvar ve ultrason bölümlerinin hazır olması gerekiyor.
        </p>
      ) : null}

      {result || storedHypotheses.length > 0 ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-bold text-slate-950">AI Değerlendirmesi</h2>
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
              Kaynak özetleri hazır. Deterministik gate AI değerlendirmesi gerektirmediyse burada yeni AI çıktısı oluşmaz.
            </p>
          )}

          {result && result.warnings.length > 0 ? (
            <p className="mt-4 text-xs leading-5 text-slate-500">
              {result.warnings.join(' ')}
            </p>
          ) : null}

          <p className="mt-5 border-t border-slate-100 pt-4 text-xs leading-5 text-slate-500">
            Bu çıktı klinik karar desteği içindir; kesin tanı veya tedavi kararı değildir ve hekim değerlendirmesi gerektirir.
          </p>
        </section>
      ) : null}
    </div>
  );
}
