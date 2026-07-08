import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import EmptyState from '../components/ui/EmptyState';
import ErrorState from '../components/ui/ErrorState';
import LoadingState from '../components/ui/LoadingState';
import SectionCard from '../components/ui/SectionCard';
import {
  getClinicalHypothesesForAnalysisRun,
  getPendingClinicalHypotheses,
  type ClinicalHypothesis,
} from '../services/clinicalHypothesesClient';
import {
  getAnalysisRunResults,
  type LabAnalysisResult,
} from '../services/labAnalysisClient';

type DashboardQueueItem = ClinicalHypothesis & {
  queue_source: 'pending_queue' | 'latest_analysis_run';
};

function statusLabel(status: string | null | undefined) {
  return (status ?? 'unknown').replace(/_/g, ' ').toUpperCase();
}

function statusClassName(status: string | null | undefined) {
  const normalizedStatus = (status ?? '').toLowerCase();

  if (
    normalizedStatus.includes('approved') ||
    normalizedStatus.includes('completed') ||
    normalizedStatus.includes('normal')
  ) {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }

  if (
    normalizedStatus.includes('rejected') ||
    normalizedStatus.includes('low') ||
    normalizedStatus.includes('high')
  ) {
    return 'border-rose-200 bg-rose-50 text-rose-700';
  }

  if (
    normalizedStatus.includes('extra') ||
    normalizedStatus.includes('test') ||
    normalizedStatus.includes('review')
  ) {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }

  if (normalizedStatus.includes('pending')) {
    return 'border-blue-200 bg-blue-50 text-blue-700';
  }

  return 'border-slate-200 bg-slate-50 text-slate-700';
}

function severityLabel(severity: string | null) {
  return (severity ?? 'low').toUpperCase();
}

function severityClassName(severity: string | null) {
  if (severity === 'high') {
    return 'border-rose-200 bg-rose-50 text-rose-700';
  }

  if (severity === 'medium') {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }

  return 'border-slate-200 bg-slate-50 text-slate-700';
}

function formatDate(value: string | null | undefined) {
  if (!value) {
    return '-';
  }

  try {
    return new Intl.DateTimeFormat('tr-TR', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function getAbnormalResults(results: LabAnalysisResult[]) {
  return results.filter(
    (result) =>
      result.result_status === 'low' || result.result_status === 'high',
  );
}

function uniqueQueueItems(items: DashboardQueueItem[]) {
  const map = new Map<string, DashboardQueueItem>();

  for (const item of items) {
    map.set(item.id, item);
  }

  return Array.from(map.values());
}

function getReviewedItems(items: DashboardQueueItem[]) {
  return items.filter((item) => !item.status.toLowerCase().includes('pending'));
}

function getPendingItems(items: DashboardQueueItem[]) {
  return items.filter((item) => item.status.toLowerCase().includes('pending'));
}

function getApprovedItems(items: DashboardQueueItem[]) {
  return items.filter((item) => item.status.toLowerCase().includes('approved'));
}

function getRejectedItems(items: DashboardQueueItem[]) {
  return items.filter((item) => item.status.toLowerCase().includes('rejected'));
}

function getExtraTestItems(items: DashboardQueueItem[]) {
  return items.filter((item) => {
    const status = item.status.toLowerCase();

    return status.includes('extra') || status.includes('test');
  });
}

export default function DashboardPage() {
  const [results, setResults] = useState<LabAnalysisResult[]>([]);
  const [queueItems, setQueueItems] = useState<DashboardQueueItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const analysisRunId = localStorage.getItem('medicore:lastAnalysisRunId');
  const labReportId = localStorage.getItem('medicore:lastLabReportId');

  useEffect(() => {
    async function loadDashboard() {
      try {
        setIsLoading(true);
        setError('');

        const pendingHypotheses = await getPendingClinicalHypotheses();

        const pendingQueueItems: DashboardQueueItem[] = pendingHypotheses.map(
          (item) => ({
            ...item,
            queue_source: 'pending_queue',
          }),
        );

        if (!analysisRunId) {
          setQueueItems(pendingQueueItems);
          setResults([]);
          return;
        }

        const [analysisResults, analysisHypotheses] = await Promise.all([
          getAnalysisRunResults(analysisRunId),
          getClinicalHypothesesForAnalysisRun(analysisRunId),
        ]);

        const analysisQueueItems: DashboardQueueItem[] = analysisHypotheses.map(
          (item) => ({
            ...item,
            queue_source: 'latest_analysis_run',
          }),
        );

        setResults(analysisResults);
        setQueueItems(uniqueQueueItems([...pendingQueueItems, ...analysisQueueItems]));
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Unable to load dashboard.',
        );
      } finally {
        setIsLoading(false);
      }
    }

    loadDashboard();
  }, [analysisRunId]);

  const abnormalResults = useMemo(() => getAbnormalResults(results), [results]);
  const pendingItems = useMemo(() => getPendingItems(queueItems), [queueItems]);
  const reviewedItems = useMemo(() => getReviewedItems(queueItems), [queueItems]);
  const approvedItems = useMemo(() => getApprovedItems(queueItems), [queueItems]);
  const rejectedItems = useMemo(() => getRejectedItems(queueItems), [queueItems]);
  const extraTestItems = useMemo(() => getExtraTestItems(queueItems), [queueItems]);

  const latestQueueItem = queueItems[0] ?? null;
  const latestResult = abnormalResults[0] ?? results[0] ?? null;

  const stats = [
    {
      label: 'Lab results',
      value: results.length,
      helper: 'Rows from latest backend analysis run',
    },
    {
      label: 'Abnormal signals',
      value: abnormalResults.length,
      helper: 'Low or high lab result statuses',
    },
    {
      label: 'Pending reviews',
      value: pendingItems.length,
      helper: 'Clinical prompts awaiting doctor action',
    },
    {
      label: 'Reviewed prompts',
      value: reviewedItems.length,
      helper: 'Doctor actions recorded',
    },
  ];

  const queueSummary = [
    {
      label: 'Approved',
      value: approvedItems.length,
      status: 'approved',
      helper: 'Accepted during doctor review',
    },
    {
      label: 'Rejected',
      value: rejectedItems.length,
      status: 'rejected',
      helper: 'Rejected during doctor review',
    },
    {
      label: 'Extra test requested',
      value: extraTestItems.length,
      status: 'extra_test_requested',
      helper: 'Needs additional follow-up testing',
    },
  ];

  if (isLoading) {
    return (
      <LoadingState
        title="Loading dashboard"
        description="Fetching backend lab results, review prompts, and doctor queue state."
      />
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Unable to load dashboard"
        description={error}
      />
    );
  }

  if (!analysisRunId && queueItems.length === 0) {
    return (
      <EmptyState
        title="No dashboard data yet"
        description="Run a backend mock analysis first to populate the dashboard."
        actionLabel="Run mock analysis"
        to="/analysis/mock"
      />
    );
  }

  return (
    <div className="space-y-8">
      <section className="rounded-lg border border-blue-100 bg-white p-6 shadow-sm lg:p-8">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase text-cyan-700">
              Backend Dashboard
            </p>

            <h2 className="mt-3 text-3xl font-semibold text-slate-950 lg:text-4xl">
              MediCore AI command center
            </h2>

            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
              Backend-connected overview for the latest analysis run, abnormal
              lab signals, clinical review prompts, and doctor review actions.
            </p>
          </div>

          <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-medium leading-6 text-blue-800 xl:max-w-sm">
            Clinical outputs are structured for physician review and are not a
            diagnosis.
          </div>
        </div>

        <div className="mt-6 grid gap-3 lg:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs text-slate-500">
            <span className="font-semibold uppercase text-slate-600">
              Analysis run:
            </span>{' '}
            {analysisRunId ?? 'No latest analysis run stored'}
          </div>

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs text-slate-500">
            <span className="font-semibold uppercase text-slate-600">
              Lab report:
            </span>{' '}
            {labReportId ?? 'No latest lab report stored'}
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {stats.map((stat) => (
          <article
            key={stat.label}
            className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
          >
            <p className="text-sm font-medium text-slate-500">{stat.label}</p>

            <p className="mt-3 text-3xl font-semibold text-slate-950">
              {stat.value}
            </p>

            <p className="mt-3 text-sm leading-6 text-slate-500">
              {stat.helper}
            </p>
          </article>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <SectionCard
          title="Doctor review queue"
          description="Backend clinical hypotheses shown as dashboard work items."
        >
          {queueItems.length === 0 ? (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              No clinical review prompts are currently available.
            </div>
          ) : (
            <div className="overflow-hidden rounded-lg border border-slate-200">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                        Prompt
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                        Severity
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                        Status
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                        Evidence
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                        Created
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                        Route
                      </th>
                    </tr>
                  </thead>

                  <tbody className="divide-y divide-slate-200 bg-white">
                    {queueItems.map((item) => (
                      <tr key={item.id}>
                        <td className="min-w-72 px-4 py-4">
                          <p className="font-medium text-slate-950">
                            {item.title}
                          </p>

                          <p className="mt-1 text-sm leading-6 text-slate-500">
                            {item.summary}
                          </p>
                        </td>

                        <td className="px-4 py-4">
                          <span
                            className={`rounded-lg border px-2.5 py-1 text-xs font-semibold ${severityClassName(
                              item.severity,
                            )}`}
                          >
                            {severityLabel(item.severity)}
                          </span>
                        </td>

                        <td className="px-4 py-4">
                          <span
                            className={`rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                              item.status,
                            )}`}
                          >
                            {statusLabel(item.status)}
                          </span>
                        </td>

                        <td className="px-4 py-4 text-slate-600">
                          {item.evidence_json.length}
                        </td>

                        <td className="px-4 py-4 text-slate-600">
                          {formatDate(item.created_at)}
                        </td>

                        <td className="px-4 py-4">
                          <Link
                            to="/doctor-worklist"
                            className="rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-2 text-sm font-medium text-cyan-800 transition hover:bg-cyan-100"
                          >
                            Open
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </SectionCard>

        <SectionCard
          title="Latest workflow state"
          description="Most recent backend item and current review breakdown."
        >
          <div className="grid gap-4">
            {latestQueueItem ? (
              <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase text-slate-500">
                      Latest queue item
                    </p>

                    <h3 className="mt-2 font-semibold text-slate-950">
                      {latestQueueItem.title}
                    </h3>
                  </div>

                  <span
                    className={`w-fit rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                      latestQueueItem.status,
                    )}`}
                  >
                    {statusLabel(latestQueueItem.status)}
                  </span>
                </div>

                <p className="mt-3 text-sm leading-6 text-slate-600">
                  {latestQueueItem.summary}
                </p>
              </article>
            ) : (
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                No queue item available yet.
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
              {queueSummary.map((item) => (
                <div
                  key={item.label}
                  className="rounded-lg border border-slate-200 bg-white p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-slate-950">
                        {item.label}
                      </p>

                      <p className="mt-1 text-sm leading-6 text-slate-500">
                        {item.helper}
                      </p>
                    </div>

                    <span
                      className={`w-fit rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                        item.status,
                      )}`}
                    >
                      {item.value}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <SectionCard
          title="Latest lab evidence"
          description="Backend lab result rows from the latest analysis run."
        >
          {results.length === 0 ? (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              No lab result rows were loaded for the latest analysis run.
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {results.map((result) => (
                <article
                  key={result.lab_result_id}
                  className={`rounded-lg border p-4 ${
                    result.result_status === 'low' ||
                    result.result_status === 'high'
                      ? 'border-blue-200 bg-blue-50'
                      : 'border-slate-200 bg-slate-50'
                  }`}
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

                    <span
                      className={`w-fit rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                        result.result_status,
                      )}`}
                    >
                      {statusLabel(result.result_status)}
                    </span>
                  </div>

                  <p className="mt-3 text-xs leading-5 text-slate-500">
                    Reference: {result.reference_min ?? '-'} -{' '}
                    {result.reference_max ?? '-'} {result.unit}
                  </p>

                  <p className="mt-3 rounded-lg border border-blue-100 bg-white p-3 text-xs leading-5 text-slate-600">
                    {result.reason}
                  </p>
                </article>
              ))}
            </div>
          )}
        </SectionCard>

        <SectionCard
          title="Quick actions"
          description="Navigation actions for backend-connected workflows."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Link
              to="/analysis/mock"
              className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-cyan-200 hover:bg-cyan-50"
            >
              <span className="font-semibold text-slate-950">
                Run mock analysis
              </span>

              <span className="mt-2 block text-sm leading-6 text-slate-500">
                Create a new backend analysis run.
              </span>
            </Link>

            <Link
              to="/analysis/results"
              className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-cyan-200 hover:bg-cyan-50"
            >
              <span className="font-semibold text-slate-950">
                View analysis results
              </span>

              <span className="mt-2 block text-sm leading-6 text-slate-500">
                Inspect latest structured lab results.
              </span>
            </Link>

            <Link
              to="/clinical-hypotheses"
              className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-cyan-200 hover:bg-cyan-50"
            >
              <span className="font-semibold text-slate-950">
                Clinical hypotheses
              </span>

              <span className="mt-2 block text-sm leading-6 text-slate-500">
                Generate or view review prompts.
              </span>
            </Link>

            <Link
              to="/doctor-review"
              className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-cyan-200 hover:bg-cyan-50"
            >
              <span className="font-semibold text-slate-950">
                Doctor review
              </span>

              <span className="mt-2 block text-sm leading-6 text-slate-500">
                Approve, reject, or request extra tests.
              </span>
            </Link>
          </div>

          {latestResult && (
            <div className="mt-4 rounded-lg border border-amber-100 bg-amber-50 p-4">
              <p className="text-xs font-semibold uppercase text-amber-700">
                Latest lab signal
              </p>

              <p className="mt-2 font-semibold text-slate-950">
                {latestResult.canonical_name ?? latestResult.raw_parameter_name}
              </p>

              <p className="mt-2 text-sm leading-6 text-slate-700">
                {latestResult.normalized_value} {latestResult.unit} ·{' '}
                {statusLabel(latestResult.result_status)}
              </p>
            </div>
          )}
        </SectionCard>
      </div>

      <SectionCard
        title="Safety framing"
        description="Dashboard data is review workflow state."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Dashboard entries are workflow records, not medical conclusions.
            </p>
          </div>

          <div className="rounded-lg border border-cyan-100 bg-cyan-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Clinical prompts stay under physician review controls.
            </p>
          </div>

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Patient-facing visibility remains blocked until review rules pass.
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