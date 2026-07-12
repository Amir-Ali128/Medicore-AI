import { useEffect, useMemo, useState, type ComponentProps } from 'react';

import EmptyState from '../components/ui/EmptyState';
import ErrorState from '../components/ui/ErrorState';
import LoadingState from '../components/ui/LoadingState';
import SectionCard from '../components/ui/SectionCard';
import StatusBadge from '../components/ui/StatusBadge';
import {
  getAnalysisRunResults,
  type LabAnalysisResult,
} from '../services/labAnalysisClient';

type BadgeStatus = ComponentProps<typeof StatusBadge>['status'];
type ResultTone = 'high' | 'low' | 'review';

function toDisplayStatus(status: LabAnalysisResult['result_status']): BadgeStatus {
  if (status === 'low') return 'LOW' as BadgeStatus;
  if (status === 'high') return 'HIGH' as BadgeStatus;
  return 'PENDING' as BadgeStatus;
}

function formatReferenceRange(result: LabAnalysisResult) {
  if (result.reference_min === null && result.reference_max === null) return '-';
  return `${result.reference_min ?? '-'} - ${result.reference_max ?? '-'} ${result.unit ?? ''}`;
}

function ResultTable({
  title,
  results,
  tone,
}: {
  title: string;
  results: LabAnalysisResult[];
  tone: ResultTone;
}) {
  if (results.length === 0) return null;

  const headerClass =
    tone === 'high'
      ? 'bg-rose-50 text-rose-800'
      : tone === 'low'
        ? 'bg-amber-50 text-amber-800'
        : 'bg-violet-50 text-violet-800';

  return (
    <section className="overflow-hidden rounded-xl border border-slate-200">
      <div
        className={`flex items-center justify-between gap-3 px-4 py-3 ${headerClass}`}
      >
        <h3 className="font-semibold">{title}</h3>
        <span className="text-sm font-semibold">{results.length} sonuç</span>
      </div>

      <div className="overflow-x-auto bg-white">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              {['Test', 'Ölçülen değer', 'Referans aralığı', 'Durum', 'Değerlendirme notu'].map(
                (heading) => (
                  <th
                    key={heading}
                    className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500"
                  >
                    {heading}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {results.map((result) => (
              <tr key={result.lab_result_id} className="bg-white">
                <td className="px-4 py-4 font-medium text-slate-950">
                  {result.canonical_name ?? result.raw_parameter_name}
                </td>
                <td className="whitespace-nowrap px-4 py-4 text-slate-600">
                  {result.normalized_value} {result.unit}
                </td>
                <td className="whitespace-nowrap px-4 py-4 text-slate-600">
                  {formatReferenceRange(result)}
                </td>
                <td className="px-4 py-4">
                  <StatusBadge status={toDisplayStatus(result.result_status)} />
                </td>
                <td className="min-w-64 px-4 py-4 text-sm leading-6 text-slate-600">
                  {result.reason || 'Sonuç hekim değerlendirmesi için hazırlanmıştır.'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function AnalysisResultsPage() {
  const [results, setResults] = useState<LabAnalysisResult[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const analysisRunId = localStorage.getItem('medicore:lastAnalysisRunId');

  useEffect(() => {
    async function loadResults() {
      try {
        setIsLoading(true);
        setError('');
        if (!analysisRunId) {
          setResults([]);
          return;
        }
        setResults(await getAnalysisRunResults(analysisRunId));
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Analiz sonuçları yüklenemedi.',
        );
      } finally {
        setIsLoading(false);
      }
    }
    void loadResults();
  }, [analysisRunId]);

  const groupedResults = useMemo(
    () => ({
      high: results.filter((result) => result.result_status === 'high'),
      low: results.filter((result) => result.result_status === 'low'),
      review: results.filter(
        (result) =>
          result.result_status === 'needs_review' ||
          result.result_status === 'unknown',
      ),
    }),
    [results],
  );

  const visibleResults = useMemo(
    () => [
      ...groupedResults.high,
      ...groupedResults.low,
      ...groupedResults.review,
    ],
    [groupedResults],
  );

  if (isLoading) {
    return (
      <LoadingState
        title="Analiz sonuçları yükleniyor"
        description="Laboratuvar sonuçları sistemden alınıyor."
      />
    );
  }

  if (error) {
    return <ErrorState title="Analiz sonuçları yüklenemedi" description={error} />;
  }

  if (!analysisRunId || results.length === 0) {
    return (
      <EmptyState
        title="Henüz analiz sonucu bulunmuyor"
        description="Önce PDF yükleyin veya manuel laboratuvar sonucu girin."
        actionLabel="Laboratuvar analizine git"
        to="/analysis/mock"
      />
    );
  }

  const summaryCards = [
    ['İşlenen sonuçlar', results.length],
    ['Yüksek sonuçlar', groupedResults.high.length],
    ['Düşük sonuçlar', groupedResults.low.length],
    ['Hekim kontrolü gerekenler', groupedResults.review.length],
  ] as const;

  return (
    <div className="space-y-8">
      <header>
        <p className="text-sm font-semibold uppercase text-cyan-700">
          Ayrıntılı sonuçlar
        </p>
        <h2 className="mt-2 text-3xl font-semibold text-slate-950">
          Anormal laboratuvar sonuçları
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          Normal sonuçlar gizlenir; yüksek, düşük ve hekim kontrolü gerektiren değerler ayrı gösterilir.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map(([title, value]) => (
          <div
            key={title}
            className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
          >
            <p className="text-sm font-medium text-slate-600">{title}</p>
            <p className="mt-3 text-3xl font-semibold text-slate-950">{value}</p>
          </div>
        ))}
      </div>

      <SectionCard title="Değerlendirme listesi" description="">
        {visibleResults.length === 0 ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-6 text-sm text-emerald-800">
            Anormal veya hekim kontrolü gerektiren sonuç bulunmadı.
          </div>
        ) : (
          <div className="space-y-5">
            <ResultTable
              title="Yüksek sonuçlar"
              results={groupedResults.high}
              tone="high"
            />
            <ResultTable
              title="Düşük sonuçlar"
              results={groupedResults.low}
              tone="low"
            />
            <ResultTable
              title="Hekim kontrolü gerekenler"
              results={groupedResults.review}
              tone="review"
            />
          </div>
        )}
      </SectionCard>
    </div>
  );
}
