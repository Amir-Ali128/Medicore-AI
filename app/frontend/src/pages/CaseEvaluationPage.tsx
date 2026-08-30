import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import ClaudeEvaluationCard from '../components/clinical/ClaudeEvaluationCard';
import {
  evaluateClaudeAbnormalResults,
  type ClaudeEvaluationHypothesis,
  type ClaudeReviewGenerationResult,
} from '../services/claudeReviewClient';
import { clearAccessToken } from '../services/authClient';
import {
  getAnalysisRunResults,
  LAST_ANALYSIS_RUN_ID_KEY,
  type ClinicalIntakeInput,
} from '../services/labAnalysisClient';
import { listPatientRadiologyReports } from '../services/radiologyClient';
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

export default function CaseEvaluationPage() {
  const navigate = useNavigate();
  const [clinicalIntake, setClinicalIntake] = useState<ClinicalIntakeInput | null>(null);
  const [labReady, setLabReady] = useState(false);
  const [radiologyReady, setRadiologyReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [result, setResult] = useState<ClaudeReviewGenerationResult | null>(null);
  const [storedHypotheses, setStoredHypotheses] = useState<ClinicalHypothesis[]>([]);
  const [error, setError] = useState('');

  const analysisRunId = localStorage.getItem(LAST_ANALYSIS_RUN_ID_KEY);
  const clinicalReady = hasClinicalData(clinicalIntake);
  const allReady = clinicalReady && labReady && radiologyReady;

  useEffect(() => {
    let cancelled = false;

    async function loadSources() {
      setLoading(true);
      setError('');

      const intake = readClinicalIntake();
      if (!cancelled) {
        setClinicalIntake(intake);
      }

      const [labsResult, reportsResult, hypothesesResult] =
        await Promise.allSettled([
          analysisRunId
            ? getAnalysisRunResults(analysisRunId)
            : Promise.resolve([]),
          listPatientRadiologyReports(),
          analysisRunId
            ? getClinicalHypothesesForAnalysisRun(analysisRunId)
            : Promise.resolve([]),
        ]);

      if (cancelled) return;

      setLabReady(
        labsResult.status === 'fulfilled' && labsResult.value.length > 0,
      );
      setRadiologyReady(
        reportsResult.status === 'fulfilled' && reportsResult.value.length > 0,
      );
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
      const nextResult = await evaluateClaudeAbnormalResults(
        analysisRunId,
        6,
        clinicalIntake,
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

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <header>
        <h1 className="text-2xl font-bold text-slate-950">Bulguları Değerlendir</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          Hasta bilgileri, laboratuvar sonuçları ve radyoloji/diğer tetkik raporları birlikte değerlendirilir.
        </p>
      </header>

      <div className="grid gap-3 md:grid-cols-3">
        <SourceStatus title="Hasta bilgileri" ready={clinicalReady} link="/patients/demo" />
        <SourceStatus title="Laboratuvar" ready={labReady} link="/analysis/mock" />
        <SourceStatus title="Radyoloji / diğer tetkikler" ready={radiologyReady} link="/radiology" />
      </div>

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
        {loading ? 'Kontrol ediliyor...' : evaluating ? 'Değerlendiriliyor...' : 'Değerlendir'}
      </button>

      {!loading && !allReady ? (
        <p className="text-sm text-slate-500">
          Değerlendirme için üç bölümün de hazır olması gerekiyor.
        </p>
      ) : null}

      {result || storedHypotheses.length > 0 ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-bold text-slate-950">Değerlendirme</h2>

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
              Değerlendirmeye uygun bir bulgu oluşturulmadı.
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
