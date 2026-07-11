import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import SectionCard from '../components/ui/SectionCard';
import DoctorLanguageSummary from '../components/DoctorLanguageSummary';
import {
  getAnalysisRunResults,
  LAST_ANALYSIS_RUN_ID_KEY,
  LAST_LAB_REPORT_ID_KEY,
  type LabAnalysisResult,
  type LabResultStatus,
} from '../services/labAnalysisClient';
import { buildDoctorInterpretation } from '../services/clinicalInterpreter';

function statusLabel(status: string) {
  return status.replace(/_/g, ' ').toUpperCase();
}

function statusClassName(status: string) {
  switch (status) {
    case 'normal':
    case 'ready':
    case 'completed':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700';
    case 'low':
    case 'high':
      return 'border-red-200 bg-red-50 text-red-700';
    case 'needs_review':
    case 'pending':
    case 'pending_review':
      return 'border-amber-200 bg-amber-50 text-amber-700';
    case 'unknown':
      return 'border-slate-200 bg-slate-50 text-slate-700';
    default:
      return 'border-blue-200 bg-blue-50 text-blue-700';
  }
}

function StatusPill({ status }: { status: LabResultStatus | string }) {
  return (
    <span
      className={`inline-flex w-fit rounded-full border px-2.5 py-1 text-xs font-semibold ${statusClassName(
        status,
      )}`}
    >
      {statusLabel(status)}
    </span>
  );
}

function formatReference(result: LabAnalysisResult) {
  if (result.reference_min === null && result.reference_max === null) {
    return 'Needs review';
  }

  return `${result.reference_min ?? '-'} - ${result.reference_max ?? '-'} ${
    result.unit
  }`;
}

function formatConfidence(value: number) {
  if (!Number.isFinite(value)) {
    return '-';
  }

  const percent = value <= 1 ? value * 100 : value;

  return `${Math.round(percent)}%`;
}

function resultReviewStatus(result: LabAnalysisResult) {
  if (result.needs_review || result.result_status === 'needs_review') {
    return 'needs_review';
  }

  if (result.result_status === 'unknown') {
    return 'unknown';
  }

  return 'ready';
}

export default function ExtractionReviewPage() {
  const [analysisRunId, setAnalysisRunId] = useState<string | null>(null);
  const [labReportId, setLabReportId] = useState<string | null>(null);
  const [results, setResults] = useState<LabAnalysisResult[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const storedAnalysisRunId = localStorage.getItem(LAST_ANALYSIS_RUN_ID_KEY);
    const storedLabReportId = localStorage.getItem(LAST_LAB_REPORT_ID_KEY);

    setAnalysisRunId(storedAnalysisRunId);
    setLabReportId(storedLabReportId);

    if (!storedAnalysisRunId) {
      setIsLoading(false);
      return;
    }

    const currentAnalysisRunId = storedAnalysisRunId;

    async function loadResults() {
      try {
        setIsLoading(true);
        setError('');

        const backendResults = await getAnalysisRunResults(currentAnalysisRunId);
        setResults(backendResults);
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Unable to load extraction review data.',
        );
      } finally {
        setIsLoading(false);
      }
    }

    void loadResults();
  }, []);

  const summary = useMemo(() => {
    const needsReview = results.filter(
      (result) =>
        result.needs_review || result.result_status === 'needs_review',
    ).length;

    const ready = results.filter(
      (result) =>
        !result.needs_review &&
        result.result_status !== 'needs_review' &&
        result.result_status !== 'unknown',
    ).length;

    const abnormal = results.filter(
      (result) => result.result_status === 'low' || result.result_status === 'high',
    ).length;

    const unknown = results.filter(
      (result) => result.result_status === 'unknown',
    ).length;

    return {
      total: results.length,
      needsReview,
      ready,
      abnormal,
      unknown,
    };
  }, [results]);

  const reviewStatus =
    summary.total === 0
      ? 'waiting'
      : summary.needsReview > 0 || summary.unknown > 0
        ? 'needs_review'
        : 'completed';

  const doctorInterpretation = useMemo(
    () => buildDoctorInterpretation(results),
    [results],
  );

  const summaryCards = [
    {
      title: 'Extracted values',
      value: summary.total,
      helper: 'Values loaded from the latest backend analysis run.',
    },
    {
      title: 'Needs review',
      value: summary.needsReview,
      helper: 'Rows where reference range or status needs human review.',
    },
    {
      title: 'Ready values',
      value: summary.ready,
      helper: 'Rows with enough backend context for review workflow.',
    },
    {
      title: 'Low / High signals',
      value: summary.abnormal,
      helper: 'Rows classified outside available reference ranges.',
    },
    {
      title: 'Unknown values',
      value: summary.unknown,
      helper: 'Rows that still need backend or reviewer clarification.',
    },
  ];

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-semibold uppercase text-cyan-700">
          Extraction Review
        </p>

        <h2 className="mt-2 text-3xl font-semibold text-slate-950">
          Backend extraction review
        </h2>

        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          Review lab values extracted from the latest backend analysis run before
          moving into clinical hypothesis and doctor review workflows.
        </p>

        <p className="mt-3 inline-flex rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-800">
          Clinical outputs are structured for physician review and are not a
          diagnosis.
        </p>
      </div>

      {!analysisRunId && !isLoading && (
        <SectionCard
          title="No backend analysis found"
          description="Run a PDF upload analysis first so this page can load real extracted values."
        >
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6">
            <p className="text-sm leading-6 text-slate-600">
              This page reads the latest analysis run saved in your browser.
              Upload a text-based PDF or run the backend sample, then return
              here.
            </p>

            <Link
              to="/analysis/mock"
              className="mt-4 inline-flex rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
            >
              Upload PDF
            </Link>
          </div>
        </SectionCard>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {isLoading && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-600">
          Loading latest extraction review data...
        </div>
      )}

      {analysisRunId && !isLoading && (
        <>
          <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
            <SectionCard
              title="Extraction job summary"
              description="Latest backend analysis context saved from PDF upload or sample analysis."
            >
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-5">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase text-slate-500">
                      Source
                    </p>
                    <h3 className="mt-2 text-xl font-semibold text-slate-950">
                      Latest backend lab report
                    </h3>
                  </div>

                  <StatusPill status={reviewStatus} />
                </div>

                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-lg border border-slate-200 bg-white p-4">
                    <p className="text-xs font-semibold uppercase text-slate-500">
                      Patient
                    </p>
                    <p className="mt-2 font-medium text-slate-950">
                      Demo Patient
                    </p>
                  </div>

                  <div className="rounded-lg border border-slate-200 bg-white p-4">
                    <p className="text-xs font-semibold uppercase text-slate-500">
                      Extracted values
                    </p>
                    <p className="mt-2 font-medium text-slate-950">
                      {summary.total}
                    </p>
                  </div>

                  <div className="rounded-lg border border-slate-200 bg-white p-4">
                    <p className="text-xs font-semibold uppercase text-slate-500">
                      Extraction status
                    </p>
                    <div className="mt-2">
                      <StatusPill status={summary.total > 0 ? 'completed' : 'waiting'} />
                    </div>
                  </div>

                  <div className="rounded-lg border border-slate-200 bg-white p-4">
                    <p className="text-xs font-semibold uppercase text-slate-500">
                      Review status
                    </p>
                    <div className="mt-2">
                      <StatusPill status={reviewStatus} />
                    </div>
                  </div>

                  <div className="rounded-lg border border-slate-200 bg-white p-4 sm:col-span-2">
                    <p className="text-xs font-semibold uppercase text-slate-500">
                      Analysis run ID
                    </p>
                    <p className="mt-2 break-all font-medium text-slate-950">
                      {analysisRunId}
                    </p>
                  </div>

                  <div className="rounded-lg border border-slate-200 bg-white p-4 sm:col-span-2">
                    <p className="text-xs font-semibold uppercase text-slate-500">
                      Lab report ID
                    </p>
                    <p className="mt-2 break-all font-medium text-slate-950">
                      {labReportId ?? 'Not available'}
                    </p>
                  </div>
                </div>
              </div>
            </SectionCard>

            <SectionCard
              title="Review summary"
              description="Counts computed from the latest backend result rows."
            >
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {summaryCards.map((card) => (
                  <div
                    key={card.title}
                    className="rounded-lg border border-slate-200 bg-slate-50 p-4"
                  >
                    <p className="text-sm font-medium text-slate-600">
                      {card.title}
                    </p>

                    <p className="mt-3 text-3xl font-semibold text-slate-950">
                      {card.value}
                    </p>

                    <p className="mt-2 text-sm leading-6 text-slate-500">
                      {card.helper}
                    </p>
                  </div>
                ))}
              </div>
            </SectionCard>
          </div>

          <SectionCard
            title="Doctor language analysis"
            description="Rule-based clinical wording generated only from Low / High backend result rows."
          >
            <DoctorLanguageSummary summary={doctorInterpretation} />
          </SectionCard>

          <SectionCard
            title="Extracted value review table"
            description="Backend extracted values prepared for human review."
          >
            {results.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-sm leading-6 text-slate-600">
                No extracted values were returned for this analysis run.
              </div>
            ) : (
              <div className="overflow-hidden rounded-lg border border-slate-200">
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-slate-200">
                    <thead className="bg-slate-50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                          Marker
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                          Extracted Value
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                          Reference Range
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                          Confidence
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                          Review Status
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                          Reviewer Note
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                          Action State
                        </th>
                      </tr>
                    </thead>

                    <tbody className="divide-y divide-slate-200 bg-white">
                      {results.map((result) => (
                        <tr key={result.lab_result_id}>
                          <td className="px-4 py-4 font-medium text-slate-950">
                            {result.canonical_name ?? result.raw_parameter_name}
                          </td>

                          <td className="px-4 py-4 text-slate-600">
                            {result.normalized_value} {result.unit}
                          </td>

                          <td className="px-4 py-4 text-slate-600">
                            {formatReference(result)}
                          </td>

                          <td className="px-4 py-4 text-slate-600">
                            {formatConfidence(result.alias_confidence)}
                          </td>

                          <td className="px-4 py-4">
                            <StatusPill status={resultReviewStatus(result)} />
                          </td>

                          <td className="min-w-64 px-4 py-4 text-slate-600">
                            {result.reason}
                          </td>

                          <td className="px-4 py-4 text-slate-600">
                            {result.needs_review ||
                            result.result_status === 'needs_review'
                              ? 'Doktor değerlendirmesi gerek'
                              : 'Ready for clinical workflow'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </SectionCard>

          <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
            <SectionCard
              title="Review actions"
              description="Continue through the backend-connected workflow."
            >
              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  {
                    label: 'View Analysis Results',
                    description:
                      'Open the structured backend result table for this run.',
                    to: '/analysis/results',
                  },
                  {
                    label: 'Create Clinical Hypothesis',
                    description:
                      'Generate a doctor-review prompt from the latest run.',
                    to: '/clinical-hypotheses',
                  },
                  {
                    label: 'Open Doctor Review',
                    description:
                      'Review pending prompts and apply a doctor action.',
                    to: '/doctor-review',
                  },
                  {
                    label: 'Upload Another PDF',
                    description:
                      'Run another backend PDF extraction and analysis.',
                    to: '/analysis/mock',
                  },
                ].map((action) => (
                  <Link
                    key={action.label}
                    to={action.to}
                    className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-blue-200 hover:bg-blue-50"
                  >
                    <span className="font-semibold text-slate-950">
                      {action.label}
                    </span>

                    <span className="mt-2 block text-sm leading-6 text-slate-500">
                      {action.description}
                    </span>
                  </Link>
                ))}
              </div>
            </SectionCard>

            <SectionCard
              title="Review guidance"
              description="Safe framing for the backend extraction review workflow."
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
                  <p className="text-sm leading-6 text-slate-700">
                    Extracted values should be checked before they influence any
                    clinical workflow.
                  </p>
                </div>

                <div className="rounded-lg border border-cyan-100 bg-cyan-50 p-4">
                  <p className="text-sm leading-6 text-slate-700">
                    Values without safe reference ranges remain in human review.
                  </p>
                </div>

                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <p className="text-sm leading-6 text-slate-700">
                    Clinical hypotheses are prepared only as review prompts.
                  </p>
                </div>

                <div className="rounded-lg border border-slate-200 bg-white p-4">
                  <p className="text-sm leading-6 text-slate-700">
                    Final decisions belong to a physician.
                  </p>
                </div>
              </div>
            </SectionCard>
          </div>
        </>
      )}
    </div>
  );
}
