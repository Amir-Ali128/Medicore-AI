import { useEffect, useState, type ComponentProps } from 'react';
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

function toDisplayStatus(
  status: LabAnalysisResult['result_status'],
): BadgeStatus {
  if (status === 'normal') {
    return 'NORMAL' as BadgeStatus;
  }

  if (status === 'low') {
    return 'LOW' as BadgeStatus;
  }

  if (status === 'high') {
    return 'HIGH' as BadgeStatus;
  }

  return 'PENDING' as BadgeStatus;
}

function getResultRowClassName(status: LabAnalysisResult['result_status']) {
  if (status === 'low') {
    return 'bg-amber-50/70';
  }

  if (status === 'high') {
    return 'bg-rose-50/70';
  }

  return 'bg-white';
}

function formatReferenceRange(result: LabAnalysisResult) {
  if (!result.reference_min && !result.reference_max) {
    return '-';
  }

  return `${result.reference_min ?? '-'} - ${result.reference_max ?? '-'} ${
    result.unit
  }`;
}

function getCounts(results: LabAnalysisResult[]) {
  return {
    total: results.length,
    normal: results.filter((result) => result.result_status === 'normal').length,
    low: results.filter((result) => result.result_status === 'low').length,
    high: results.filter((result) => result.result_status === 'high').length,
    unknown: results.filter((result) => result.result_status === 'unknown')
      .length,
    needsReview: results.filter((result) => result.needs_review).length,
  };
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

        const data = await getAnalysisRunResults(analysisRunId);
        setResults(data);
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Unable to load analysis results.',
        );
      } finally {
        setIsLoading(false);
      }
    }

    loadResults();
  }, [analysisRunId]);

  if (isLoading) {
    return (
      <LoadingState
        title="Loading analysis results"
        description="Fetching structured lab signals from the backend."
      />
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Unable to load analysis results"
        description={error}
      />
    );
  }

  if (!analysisRunId || results.length === 0) {
    return (
      <EmptyState
        title="No backend analysis results yet"
        description="Run backend mock analysis first, then return here to review structured results."
        actionLabel="Open mock analysis"
        to="/analysis/mock"
      />
    );
  }

  const counts = getCounts(results);

  const summaryCards = [
    {
      title: 'Total lab results',
      value: counts.total,
      helper: 'Backend analysis results',
    },
    {
      title: 'Normal results',
      value: counts.normal,
      helper: 'Results inside reference range',
    },
    {
      title: 'Flagged results',
      value: counts.low + counts.high,
      helper: 'LOW or HIGH structured lab signals',
    },
    {
      title: 'Needs review',
      value: counts.needsReview,
      helper: 'Results marked for physician review',
    },
  ];

  const abnormalResults = results.filter(
    (result) =>
      result.result_status === 'low' || result.result_status === 'high',
  );

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-semibold uppercase text-cyan-700">
          Results
        </p>

        <h2 className="mt-2 text-3xl font-semibold text-slate-950">
          Structured analysis results
        </h2>

        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          Backend-connected lab result review screen with deterministic status
          labels, structured lab signals, and physician review framing.
        </p>

        <p className="mt-3 inline-flex rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-800">
          Clinical outputs are structured for physician review and are not a
          diagnosis.
        </p>

        <div className="mt-4 rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-500">
          <p>Analysis run ID: {analysisRunId}</p>
          {labReportId && <p>Lab report ID: {labReportId}</p>}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map((card) => (
          <div
            key={card.title}
            className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
          >
            <p className="text-sm font-medium text-slate-600">{card.title}</p>

            <p className="mt-3 text-3xl font-semibold text-slate-950">
              {card.value}
            </p>

            <p className="mt-2 text-sm leading-6 text-slate-500">
              {card.helper}
            </p>
          </div>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
        <SectionCard
          title="Structured lab result table"
          description="Backend values with deterministic status labels and review notes."
        >
          <div className="overflow-hidden rounded-lg border border-slate-200">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Marker
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Measured Value
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Reference Range
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Status Label
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Review Note
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-slate-200">
                  {results.map((result) => (
                    <tr
                      key={result.lab_result_id}
                      className={getResultRowClassName(result.result_status)}
                    >
                      <td className="px-4 py-4 font-medium text-slate-950">
                        {result.canonical_name ?? result.raw_parameter_name}
                      </td>

                      <td className="px-4 py-4 text-slate-600">
                        {result.normalized_value} {result.unit}
                      </td>

                      <td className="px-4 py-4 text-slate-600">
                        {formatReferenceRange(result)}
                      </td>

                      <td className="px-4 py-4">
                        <StatusBadge
                          status={toDisplayStatus(result.result_status)}
                        />
                      </td>

                      <td className="min-w-64 px-4 py-4 text-slate-600">
                        {result.reason ||
                          'Structured lab signal prepared for physician review.'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </SectionCard>

        <SectionCard
          title="Abnormal signal panel"
          description="LOW and HIGH backend lab results shown as review prompts."
        >
          {abnormalResults.length === 0 ? (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              No LOW or HIGH results in the latest backend analysis.
            </div>
          ) : (
            <div className="space-y-4">
              {abnormalResults.map((result) => (
                <article
                  key={result.lab_result_id}
                  className="rounded-lg border border-slate-200 bg-slate-50 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="font-semibold text-slate-950">
                        {result.canonical_name ?? result.raw_parameter_name}
                      </h3>

                      <p className="mt-2 text-sm text-slate-600">
                        {result.normalized_value} {result.unit}
                      </p>
                    </div>

                    <StatusBadge
                      status={toDisplayStatus(result.result_status)}
                    />
                  </div>

                  <p className="mt-3 text-sm text-slate-500">
                    Reference range: {formatReferenceRange(result)}
                  </p>

                  <p className="mt-3 rounded-lg border border-blue-100 bg-white p-3 text-sm leading-6 text-slate-600">
                    {result.reason}
                  </p>
                </article>
              ))}
            </div>
          )}
        </SectionCard>
      </div>

      <SectionCard
        title="Backend confidence"
        description="Confidence values returned by the analysis pipeline."
      >
        <div className="grid gap-4 md:grid-cols-3">
          {results.map((result) => (
            <article
              key={`${result.lab_result_id}-confidence`}
              className="rounded-lg border border-slate-200 bg-slate-50 p-4"
            >
              <h3 className="font-semibold text-slate-950">
                {result.canonical_name ?? result.raw_parameter_name}
              </h3>

              <div className="mt-4 space-y-2 text-sm text-slate-600">
                <p>Alias confidence: {result.alias_confidence}</p>
                <p>Reference confidence: {result.reference_confidence}</p>
                <p>
                  Classification confidence:{' '}
                  {result.classification_confidence}
                </p>
                <p>Trend confidence: {result.trend_confidence}</p>
              </div>
            </article>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Review actions"
        description="Navigate to the next physician-review workflow step."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Link
            to="/clinical-hypotheses"
            className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-blue-200 hover:bg-blue-50"
          >
            <span className="font-semibold text-slate-950">
              Generate clinical hypotheses
            </span>

            <span className="mt-2 block text-sm leading-6 text-slate-500">
              Continue to structured physician-review prompts.
            </span>
          </Link>

          <Link
            to="/analysis/mock"
            className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-blue-200 hover:bg-blue-50"
          >
            <span className="font-semibold text-slate-950">
              Run another mock analysis
            </span>

            <span className="mt-2 block text-sm leading-6 text-slate-500">
              Return to the backend-connected mock analysis workspace.
            </span>
          </Link>
        </div>
      </SectionCard>

      <SectionCard
        title="Safety framing"
        description="Structured outputs remain review-oriented."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              LOW, NORMAL, and HIGH labels are deterministic backend labels.
            </p>
          </div>

          <div className="rounded-lg border border-cyan-100 bg-cyan-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              AI does not determine final diagnosis.
            </p>
          </div>

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Outputs are prepared for doctor review.
            </p>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-sm leading-6 text-slate-700">
              Final clinical decisions belong to a physician.
            </p>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}