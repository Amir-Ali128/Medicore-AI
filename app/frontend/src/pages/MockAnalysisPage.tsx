import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import SectionCard from '../components/ui/SectionCard';
import {
  runBackendMockAnalysis,
  uploadLabReportPdf,
  type LabAnalysisResponse,
  type LabAnalysisResult,
  type LabResultStatus,
} from '../services/labAnalysisClient';

function statusLabel(status: string) {
  return status.replace(/_/g, ' ').toUpperCase();
}

function statusClassName(status: string) {
  switch (status) {
    case 'normal':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700';
    case 'low':
    case 'high':
      return 'border-red-200 bg-red-50 text-red-700';
    case 'needs_review':
      return 'border-amber-200 bg-amber-50 text-amber-700';
    default:
      return 'border-slate-200 bg-slate-50 text-slate-700';
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

function countAbnormal(results: LabAnalysisResult[]) {
  return results.filter(
    (result) => result.result_status === 'low' || result.result_status === 'high',
  ).length;
}

export default function MockAnalysisPage() {
  const navigate = useNavigate();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [backendResult, setBackendResult] =
    useState<LabAnalysisResponse | null>(null);
  const [backendError, setBackendError] = useState('');
  const [isBackendRunning, setIsBackendRunning] = useState(false);
  const [isPdfUploading, setIsPdfUploading] = useState(false);

  const firstBackendResult = backendResult?.results[0] ?? null;
  const abnormalCount = backendResult ? countAbnormal(backendResult.results) : 0;

  const summaryCards = [
    {
      title: 'Extracted values',
      value: backendResult?.counts.total ?? 0,
      helper: 'Values returned by the backend analysis pipeline.',
    },
    {
      title: 'Needs review',
      value: backendResult?.counts.needs_review ?? 0,
      helper: 'Values where reference range or classification needs review.',
    },
    {
      title: 'Low / High signals',
      value: abnormalCount,
      helper: 'Values classified outside available reference range.',
    },
    {
      title: 'Normal values',
      value: backendResult?.counts.normal ?? 0,
      helper: 'Values classified as normal by backend rules.',
    },
  ];

  async function handleRunBackendAnalysis() {
    try {
      setIsBackendRunning(true);
      setBackendError('');

      const result = await runBackendMockAnalysis();
      setBackendResult(result);
    } catch (error) {
      setBackendError(
        error instanceof Error ? error.message : 'Backend analysis failed.',
      );
    } finally {
      setIsBackendRunning(false);
    }
  }

  async function handleUploadPdf() {
    if (!selectedFile) {
      setBackendError('Please choose a PDF file first.');
      return;
    }

    try {
      setIsPdfUploading(true);
      setBackendError('');

      const result = await uploadLabReportPdf(selectedFile);
      setBackendResult(result);
    } catch (error) {
      setBackendError(
        error instanceof Error ? error.message : 'PDF upload analysis failed.',
      );
    } finally {
      setIsPdfUploading(false);
    }
  }

  function handleGoToResults() {
    if (!backendResult) {
      return;
    }

    navigate('/analysis/results');
  }

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-semibold uppercase text-cyan-700">
          Backend Analysis
        </p>

        <h2 className="mt-2 text-3xl font-semibold text-slate-950">
          Lab report analysis workspace
        </h2>

        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          Upload a text-based PDF lab report or run the controlled backend
          analysis sample. Results are saved to the latest analysis workflow.
        </p>

        <p className="mt-3 inline-flex rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-800">
          Clinical outputs are structured for physician review and are not a
          diagnosis.
        </p>
      </div>

      <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
        <div className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
          <div>
            <p className="text-sm font-semibold uppercase text-emerald-700">
              PDF upload
            </p>

            <h2 className="mt-1 text-xl font-semibold text-slate-950">
              Upload PDF & analyze with backend
            </h2>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Select a text-based PDF. The backend extracts selectable text,
              parses supported lab values, stores the analysis run, and returns
              structured results.
            </p>

            <div className="mt-4 rounded-lg border border-dashed border-emerald-300 bg-white p-4">
              <input
                type="file"
                accept="application/pdf,.pdf"
                onChange={(event) =>
                  setSelectedFile(event.target.files?.[0] ?? null)
                }
                className="block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-slate-950 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-slate-800"
              />

              {selectedFile && (
                <p className="mt-3 text-sm text-slate-600">
                  Selected:{' '}
                  <span className="font-semibold text-slate-950">
                    {selectedFile.name}
                  </span>
                </p>
              )}

              <button
                type="button"
                onClick={handleUploadPdf}
                disabled={isPdfUploading || !selectedFile}
                className="mt-4 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isPdfUploading ? 'Uploading & analyzing...' : 'Upload & Analyze PDF'}
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <p className="text-sm font-semibold uppercase text-slate-500">
              Controlled backend sample
            </p>

            <h3 className="mt-2 text-lg font-semibold text-slate-950">
              Run demo Hemoglobin payload
            </h3>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Sends a fixed Hemoglobin sample to the existing FastAPI pipeline.
              Use this when you want to verify that backend analysis still works.
            </p>

            <button
              type="button"
              onClick={handleRunBackendAnalysis}
              disabled={isBackendRunning}
              className="mt-4 rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isBackendRunning ? 'Running...' : 'Run Backend Analysis'}
            </button>
          </div>
        </div>

        {backendError && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {backendError}
          </div>
        )}

        {backendResult && (
          <div className="mt-4 rounded-lg border border-emerald-200 bg-white p-4 text-sm text-slate-700">
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div>
                <p className="text-sm font-semibold text-slate-950">
                  Analysis completed
                </p>
                <p className="mt-1 text-sm text-slate-600">
                  Latest run was saved and can be opened from Results,
                  Clinical Hypotheses, Worklist, Timeline, and Patient Detail.
                </p>
              </div>

              <button
                type="button"
                onClick={handleGoToResults}
                className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-800"
              >
                View Analysis Results
              </button>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-5">
              <div>
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Total
                </p>
                <p className="mt-1 text-2xl font-semibold text-slate-950">
                  {backendResult.counts.total}
                </p>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Low
                </p>
                <p className="mt-1 text-2xl font-semibold text-red-600">
                  {backendResult.counts.low}
                </p>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase text-slate-500">
                  High
                </p>
                <p className="mt-1 text-2xl font-semibold text-red-600">
                  {backendResult.counts.high}
                </p>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Needs review
                </p>
                <p className="mt-1 text-2xl font-semibold text-amber-700">
                  {backendResult.counts.needs_review}
                </p>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Normal
                </p>
                <p className="mt-1 text-2xl font-semibold text-emerald-700">
                  {backendResult.counts.normal}
                </p>
              </div>
            </div>

            {firstBackendResult && (
              <div className="mt-4 rounded-lg bg-slate-50 p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="font-semibold text-slate-950">
                      {firstBackendResult.canonical_name ??
                        firstBackendResult.raw_parameter_name}
                      : {firstBackendResult.normalized_value}{' '}
                      {firstBackendResult.unit}
                    </p>

                    <p className="mt-1 text-sm text-slate-600">
                      Reference: {formatReference(firstBackendResult)}
                    </p>
                  </div>

                  <StatusPill status={firstBackendResult.result_status} />
                </div>

                <p className="mt-3 text-sm text-slate-600">
                  {firstBackendResult.reason}
                </p>
              </div>
            )}

            <div className="mt-4 text-xs text-slate-500">
              <p>Analysis run ID: {backendResult.analysis_run_id}</p>
              <p>Lab report ID: {backendResult.lab_report_id}</p>
            </div>
          </div>
        )}
      </section>

      <SectionCard
        title="Backend analysis summary"
        description="Computed from the latest backend response in this browser session."
      >
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
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

      <SectionCard
        title="Extracted result preview"
        description="Values returned by the backend analysis endpoint."
      >
        {!backendResult ? (
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-sm leading-6 text-slate-600">
            Upload a PDF or run the backend analysis sample to preview extracted
            results here.
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
                      Value
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Reference
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Reason
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-slate-200 bg-white">
                  {backendResult.results.map((result) => (
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
                      <td className="px-4 py-4">
                        <StatusPill status={result.result_status} />
                      </td>
                      <td className="max-w-md px-4 py-4 text-sm leading-6 text-slate-600">
                        {result.reason}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </SectionCard>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <SectionCard
          title="Workflow after analysis"
          description="Use the latest backend run across the review screens."
        >
          <div className="grid gap-4 md:grid-cols-2">
            {[
              {
                title: '1. Analyze PDF',
                description:
                  'Upload a text-based PDF and let the backend create the analysis run.',
                status: backendResult ? 'completed' : 'ready',
              },
              {
                title: '2. Review results',
                description:
                  'Open the Results page to inspect all parsed values and status labels.',
                status: backendResult ? 'available' : 'waiting',
              },
              {
                title: '3. Create clinical prompt',
                description:
                  'Use Clinical Hypotheses to create a physician-review prompt from the latest run.',
                status: backendResult ? 'available' : 'waiting',
              },
              {
                title: '4. Doctor review',
                description:
                  'Approve, reject, or request extra tests from the doctor review queue.',
                status: backendResult ? 'available' : 'waiting',
              },
            ].map((step) => (
              <article
                key={step.title}
                className="rounded-lg border border-slate-200 bg-slate-50 p-4"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <h3 className="font-semibold text-slate-950">
                    {step.title}
                  </h3>

                  <span className="inline-flex w-fit rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold uppercase text-slate-600">
                    {step.status}
                  </span>
                </div>

                <p className="mt-3 text-sm leading-6 text-slate-600">
                  {step.description}
                </p>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Safe actions"
          description="Navigate through the backend-connected workflow."
        >
          <div className="space-y-3">
            {[
              {
                label: 'View Analysis Results',
                description: 'Open all lab results for the latest analysis run.',
                to: '/analysis/results',
                disabled: !backendResult,
              },
              {
                label: 'Create Clinical Hypothesis',
                description: 'Generate a structured doctor-review prompt.',
                to: '/clinical-hypotheses',
                disabled: !backendResult,
              },
              {
                label: 'Open Doctor Review',
                description: 'Review pending prompts and apply a doctor action.',
                to: '/doctor-review',
                disabled: false,
              },
              {
                label: 'Open Timeline',
                description: 'See analysis and review events over time.',
                to: '/timeline',
                disabled: false,
              },
            ].map((action) => {
              const content = (
                <>
                  <span className="font-semibold text-slate-950">
                    {action.label}
                  </span>
                  <span className="mt-2 block text-sm leading-6 text-slate-500">
                    {action.description}
                  </span>
                </>
              );

              if (action.disabled) {
                return (
                  <button
                    key={action.label}
                    type="button"
                    disabled
                    className="block w-full cursor-not-allowed rounded-lg border border-slate-200 bg-slate-50 p-4 text-left opacity-60"
                  >
                    {content}
                  </button>
                );
              }

              return (
                <Link
                  key={action.label}
                  to={action.to}
                  className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-blue-200 hover:bg-blue-50"
                >
                  {content}
                </Link>
              );
            })}
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="Safety framing"
        description="Clinical outputs stay review-oriented in this module."
      >
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              The backend labels results only when a reference range is safely
              available.
            </p>
          </div>

          <div className="rounded-lg border border-cyan-100 bg-cyan-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Values with uncertain reference ranges are routed for human review.
            </p>
          </div>

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Final clinical decisions belong to a physician.
            </p>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}