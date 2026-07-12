import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  evaluateClaudeAbnormalResults,
  type ClaudeEvaluationHypothesis,
  type ClaudeReviewGenerationResult,
} from '../../services/claudeReviewClient';
import {
  getClinicalHypothesesForAnalysisRun,
  type ClinicalHypothesis,
} from '../../services/clinicalHypothesesClient';
import {
  getAnalysisRunResults,
  type LabAnalysisResult,
} from '../../services/labAnalysisClient';
import { listPatientRadiologyReports } from '../../services/radiologyClient';
import ClaudeEvaluationCard from './ClaudeEvaluationCard';

function isNonNormal(result: LabAnalysisResult) {
  return result.result_status !== 'normal';
}

function asClaudeHypothesis(
  hypothesis: ClinicalHypothesis,
): ClaudeEvaluationHypothesis {
  return {
    ...hypothesis,
    metadata_json:
      'metadata_json' in hypothesis &&
      typeof hypothesis.metadata_json === 'object' &&
      hypothesis.metadata_json !== null
        ? (hypothesis.metadata_json as Record<string, unknown>)
        : {},
  } as ClaudeEvaluationHypothesis;
}

export default function UnifiedClinicalEvaluationPanel() {
  const analysisRunId = localStorage.getItem('medicore:lastAnalysisRunId');
  const [hypotheses, setHypotheses] = useState<ClinicalHypothesis[]>([]);
  const [labResults, setLabResults] = useState<LabAnalysisResult[]>([]);
  const [radiologyCount, setRadiologyCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function loadPanel() {
    setIsLoading(true);
    setError('');
    try {
      const [reports, results, reviews] = await Promise.all([
        listPatientRadiologyReports().catch(() => []),
        analysisRunId
          ? getAnalysisRunResults(analysisRunId).catch(() => [])
          : Promise.resolve([]),
        analysisRunId
          ? getClinicalHypothesesForAnalysisRun(analysisRunId).catch(() => [])
          : Promise.resolve([]),
      ]);
      setRadiologyCount(reports.length);
      setLabResults(results);
      setHypotheses(reviews);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : 'Birleşik değerlendirme yüklenemedi.',
      );
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadPanel();
  }, [analysisRunId]);

  const abnormalResults = useMemo(
    () => labResults.filter(isNonNormal),
    [labResults],
  );

  async function handleEvaluate() {
    if (!analysisRunId || abnormalResults.length === 0) return;
    setIsEvaluating(true);
    setError('');
    setNotice('');
    try {
      const result: ClaudeReviewGenerationResult =
        await evaluateClaudeAbnormalResults(
          analysisRunId,
          Math.min(Math.max(abnormalResults.length, 1), 10),
        );
      setNotice(
        result.created_count > 0
          ? `${result.created_count} yeni hekim değerlendirmesi oluşturuldu.`
          : 'Yeni değerlendirme oluşturulmadı. Mevcut veriler veya güvenlik kontrolleri yetersiz olabilir.',
      );
      await loadPanel();
    } catch (evaluationError) {
      setError(
        evaluationError instanceof Error
          ? evaluationError.message
          : 'Claude değerlendirmesi tamamlanamadı.',
      );
    } finally {
      setIsEvaluating(false);
    }
  }

  return (
    <section className="mt-6 rounded-xl border border-violet-200 bg-violet-50/60 p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-wide text-violet-700">
            Birleşik klinik değerlendirme
          </p>
          <h3 className="mt-2 text-xl font-semibold text-slate-950">
            Tüm hasta verilerini birlikte değerlendir
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            Claude; hasta bilgileri, şikâyetler, belirtiler, tıbbi öykü, muayene ve yaşamsal bulgular, anormal laboratuvar sonuçları ile radyoloji ve DEXA raporlarını aynı klinik bağlamda kullanır.
          </p>
        </div>
        <button
          type="button"
          onClick={handleEvaluate}
          disabled={
            !analysisRunId || abnormalResults.length === 0 || isEvaluating
          }
          className="shrink-0 rounded-lg bg-violet-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isEvaluating ? 'Değerlendiriliyor…' : 'Tüm verilerle değerlendir'}
        </button>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold uppercase text-slate-500">Klinik kayıt</p>
          <p className="mt-2 font-semibold text-emerald-700">Dahil</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold uppercase text-slate-500">Laboratuvar</p>
          <p className="mt-2 font-semibold text-slate-900">
            {abnormalResults.length} anormal / kontrol gereken
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold uppercase text-slate-500">Radyoloji ve DEXA</p>
          <p className="mt-2 font-semibold text-slate-900">{radiologyCount} rapor</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold uppercase text-slate-500">Hekim yorumları</p>
          <p className="mt-2 font-semibold text-slate-900">{hypotheses.length} kayıt</p>
        </div>
      </div>

      {!analysisRunId ? (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          Birleşik değerlendirme için önce Laboratuvar bölümünde bir analiz oluşturun.
        </div>
      ) : abnormalResults.length === 0 && !isLoading ? (
        <div className="mt-4 rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600">
          Claude değerlendirmesi için anormal veya hekim kontrolü gereken laboratuvar sonucu bulunmuyor.
        </div>
      ) : null}

      {notice ? (
        <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
          {notice}
        </div>
      ) : null}
      {error ? (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      <div className="mt-5 flex items-center justify-between gap-3">
        <h4 className="font-semibold text-slate-950">Claude klinik yorumları</h4>
        <Link
          to="/clinical-hypotheses"
          className="text-sm font-semibold text-violet-700 hover:text-violet-900"
        >
          Tüm yorumları aç
        </Link>
      </div>

      {isLoading ? (
        <p className="mt-3 text-sm text-slate-500">Değerlendirmeler yükleniyor…</p>
      ) : hypotheses.length === 0 ? (
        <div className="mt-3 rounded-lg border border-dashed border-violet-200 bg-white p-5 text-sm text-slate-600">
          Henüz birleşik klinik değerlendirme oluşturulmadı.
        </div>
      ) : (
        <div className="mt-3 space-y-4">
          {hypotheses.slice(0, 5).map((hypothesis) => (
            <ClaudeEvaluationCard
              key={hypothesis.id}
              hypothesis={asClaudeHypothesis(hypothesis)}
            />
          ))}
        </div>
      )}

      <p className="mt-4 text-xs leading-5 text-slate-500">
        Bu çıktılar tanı veya tedavi kararı değildir. Orijinal klinik kayıtlar, laboratuvar sonuçları ve görüntüleme raporlarıyla birlikte hekim tarafından doğrulanmalıdır.
      </p>
    </section>
  );
}
