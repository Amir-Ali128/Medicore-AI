import { useEffect, useMemo, useState, type ComponentProps } from 'react';
import { Link } from 'react-router-dom';

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
  description,
  results,
  tone,
}: {
  title: string;
  description: string;
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
      <div className={`flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between ${headerClass}`}>
        <div>
          <h3 className="font-semibold">{title}</h3>
          <p className="mt-1 text-sm opacity-80">{description}</p>
        </div>
        <span className="text-sm font-semibold">{results.length} result(s)</span>
      </div>

      <div className="overflow-x-auto bg-white">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              {['Marker', 'Measured value', 'Reference range', 'Status', 'Review note'].map((heading) => (
                <th key={heading} className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                  {heading}
                </th>
              ))}
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
                <td className="whitespace-nowrap px-4 py-4 text-slate-600">{formatReferenceRange(result)}</td>
                <td className="px-4 py-4"><StatusBadge status={toDisplayStatus(result.result_status)} /></td>
                <td className="min-w-64 px-4 py-4 text-sm leading-6 text-slate-600">
                  {result.reason || 'Structured lab signal prepared for physician review.'}
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
  const labReportId = localStorage.getItem('medicore:lastLabReportId');

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
        setError(loadError instanceof Error ? loadError.message : 'Unable to load analysis results.');
      } finally {
        setIsLoading(false);
      }
    }
    loadResults();
  }, [analysisRunId]);

  const groupedResults = useMemo(() => ({
    high: results.filter((result) => result.result_status === 'high'),
    low: results.filter((result) => result.result_status === 'low'),
    review: results.filter(
      (result) => result.result_status === 'needs_review' || result.result_status === 'unknown',
    ),
  }), [results]);

  const visibleResults = useMemo(
    () => [...groupedResults.high, ...groupedResults.low, ...groupedResults.review],
    [groupedResults],
  );

  if (isLoading) {
    return <LoadingState title="Loading analysis results" description="Fetching structured lab signals from the backend." />;
  }

  if (error) {
    return <ErrorState title="Unable to load analysis results" description={error} />;
  }

  if (!analysisRunId || results.length === 0) {
    return (
      <EmptyState
        title="No backend analysis results yet"
        description="Upload a PDF or enter manual results first, then return here."
        actionLabel="Open lab analysis"
        to="/analysis/mock"
      />
    );
  }

  const summaryCards = [
    ['Processed results', results.length, 'All values stored by the backend pipeline.'],
    ['High signals', groupedResults.high.length, 'Results above an available reference range.'],
    ['Low signals', groupedResults.low.length, 'Results below an available reference range.'],
    ['Needs review', groupedResults.review.length, 'Unknown or uncertain structured results.'],
  ] as const;

  return (
    <div className="space-y-8">
      <header>
        <p className="text-sm font-semibold uppercase text-cyan-700">Results</p>
        <h2 className="mt-2 text-3xl font-semibold text-slate-950">Abnormal analysis results</h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          This review page hides normal result rows and separates HIGH, LOW, and uncertain values for physician review.
        </p>
        <p className="mt-3 inline-flex rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-800">
          Status labels are deterministic backend outputs. Final clinical decisions belong to a physician.
        </p>
        <div className="mt-4 rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-500">
          <p>Analysis run ID: {analysisRunId}</p>
          {labReportId && <p>Lab report ID: {labReportId}</p>}
        </div>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map(([title, value, helper]) => (
          <div key={title} className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-slate-600">{title}</p>
            <p className="mt-3 text-3xl font-semibold text-slate-950">{value}</p>
            <p className="mt-2 text-sm leading-6 text-slate-500">{helper}</p>
          </div>
        ))}
      </div>

      <SectionCard
        title="Separated review queue"
        description="Normal values are intentionally hidden from this page."
      >
        {visibleResults.length === 0 ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-6 text-sm text-emerald-800">
            No abnormal or review-required result was found. Normal rows remain hidden by design.
          </div>
        ) : (
          <div className="space-y-5">
            <ResultTable title="High results" description="Above the available reference range." results={groupedResults.high} tone="high" />
            <ResultTable title="Low results" description="Below the available reference range." results={groupedResults.low} tone="low" />
            <ResultTable title="Needs review" description="Unknown mapping, range, or classification." results={groupedResults.review} tone="review" />
          </div>
        )}
      </SectionCard>

      {visibleResults.length > 0 && (
        <SectionCard title="Backend confidence" description="Confidence values for visible non-normal results only.">
          <div className="grid gap-4 md:grid-cols-3">
            {visibleResults.map((result) => (
              <article key={`${result.lab_result_id}-confidence`} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <h3 className="font-semibold text-slate-950">{result.canonical_name ?? result.raw_parameter_name}</h3>
                <div className="mt-4 space-y-2 text-sm text-slate-600">
                  <p>Alias confidence: {result.alias_confidence}</p>
                  <p>Reference confidence: {result.reference_confidence}</p>
                  <p>Classification confidence: {result.classification_confidence}</p>
                  <p>Trend confidence: {result.trend_confidence}</p>
                </div>
              </article>
            ))}
          </div>
        </SectionCard>
      )}

      <SectionCard title="Review actions" description="Continue through the physician-review workflow.">
        <div className="grid gap-3 sm:grid-cols-2">
          <Link to="/analysis/mock" className="rounded-lg border border-violet-200 bg-violet-50 p-4 hover:bg-violet-100">
            <span className="font-semibold text-slate-950">Generate Claude review</span>
            <span className="mt-2 block text-sm leading-6 text-slate-500">Return to Lab Analysis and generate hypotheses from non-normal results only.</span>
          </Link>
          <Link to="/clinical-hypotheses" className="rounded-lg border border-slate-200 bg-white p-4 hover:border-blue-200 hover:bg-blue-50">
            <span className="font-semibold text-slate-950">Open clinical review prompts</span>
            <span className="mt-2 block text-sm leading-6 text-slate-500">Review persisted physician-review hypotheses and evidence.</span>
          </Link>
        </div>
      </SectionCard>
    </div>
  );
}
