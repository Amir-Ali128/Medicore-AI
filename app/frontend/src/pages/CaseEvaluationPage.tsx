import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  evaluateClaudeAbnormalResults,
  type ClaudeReviewGenerationResult,
} from '../services/claudeReviewClient';
import {
  getAnalysisRunResults,
  LAST_ANALYSIS_RUN_ID_KEY,
  type ClinicalIntakeInput,
} from '../services/labAnalysisClient';
import { listPatientRadiologyReports } from '../services/radiologyClient';

const ACTIVE_CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';

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
  const [clinicalIntake, setClinicalIntake] = useState<ClinicalIntakeInput | null>(null);
  const [labReady, setLabReady] = useState(false);
  const [radiologyReady, setRadiologyReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [result, setResult] = useState<ClaudeReviewGenerationResult | null>(null);
  const [error, setError] = useState('');

  const analysisRunId = localStorage.getItem(LAST_ANALYSIS_RUN_ID_KEY);
  const clinicalReady = hasClinicalData(clinicalIntake);
  const allReady = clinicalReady && labReady && radiologyReady;

  useEffect(() => {
    let cancelled = false;

    async function loadSources() {
      try {
        setLoading(true);
        setError('');
        const intake = readClinicalIntake();
        const [labs, reports] = await Promise.all([
          analysisRunId ? getAnalysisRunResults(analysisRunId) : Promise.resolve([]),
          listPatientRadiologyReports(),
        ]);

        if (cancelled) return;
        setClinicalIntake(intake);
        setLabReady(labs.length > 0);
        setRadiologyReady(reports.length > 0);
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Kayıtlı bilgiler yüklenemedi.',
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadSources();
    return () => {
      cancelled = true;
    };
  }, [analysisRunId]);

  const findings = useMemo(() => {
    if (!result) return [];
    const hypotheses = result.created_hypotheses?.length
      ? result.created_hypotheses
      : result.hypotheses ?? [];

    return hypotheses.map((item) => ({
      id: item.id,
      title: item.title,
      summary: item.summary,
    }));
  }, [result]);

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
    } catch (evaluationError) {
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

      {result ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-bold text-slate-950">Değerlendirme</h2>

          {findings.length > 0 ? (
            <div className="mt-4 space-y-3">
              {findings.map((finding) => (
                <div key={finding.id} className="rounded-xl bg-slate-50 p-4">
                  <p className="font-semibold text-slate-900">{finding.title}</p>
                  <p className="mt-1 text-sm leading-6 text-slate-600">{finding.summary}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-4 text-sm leading-6 text-slate-600">
              Değerlendirmeye uygun bir bulgu oluşturulmadı.
            </p>
          )}

          {result.warnings.length > 0 ? (
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
