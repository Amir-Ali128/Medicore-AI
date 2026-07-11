import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import SectionCard from '../components/ui/SectionCard';
import {
  runBackendMockAnalysis,
  submitManualLabResults,
  uploadLabReportPdf,
  type LabAnalysisResponse,
  type LabAnalysisResult,
  type LabResultStatus,
  type ManualLabValueInput,
} from '../services/labAnalysisClient';

type ManualRow = {
  id: string;
  parameterName: string;
  value: string;
  unit: string;
  referenceMin: string;
  referenceMax: string;
  measuredAt: string;
};

function todayValue() {
  return new Date().toISOString().slice(0, 10);
}

function createManualRow(): ManualRow {
  return {
    id: crypto.randomUUID(),
    parameterName: '',
    value: '',
    unit: '',
    referenceMin: '',
    referenceMax: '',
    measuredAt: todayValue(),
  };
}

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

function parseOptionalNumber(value: string): number | null {
  if (!value.trim()) {
    return null;
  }

  const parsed = Number(value.replace(',', '.'));

  if (!Number.isFinite(parsed)) {
    throw new Error(`"${value}" is not a valid number.`);
  }

  return parsed;
}

function toManualValue(row: ManualRow): ManualLabValueInput {
  const parameterName = row.parameterName.trim();
  const unit = row.unit.trim();

  if (!parameterName) {
    throw new Error('Every manual result needs a test name.');
  }

  if (!row.value.trim()) {
    throw new Error(`${parameterName}: result value is required.`);
  }

  const normalizedValue = Number(row.value.replace(',', '.'));

  if (!Number.isFinite(normalizedValue)) {
    throw new Error(`${parameterName}: result value must be numeric.`);
  }

  if (!unit) {
    throw new Error(`${parameterName}: unit is required.`);
  }

  const referenceMin = parseOptionalNumber(row.referenceMin);
  const referenceMax = parseOptionalNumber(row.referenceMax);

  if (
    referenceMin !== null &&
    referenceMax !== null &&
    referenceMin > referenceMax
  ) {
    throw new Error(
      `${parameterName}: reference minimum cannot be greater than maximum.`,
    );
  }

  return {
    raw_parameter_name: parameterName,
    normalized_value: normalizedValue,
    unit,
    extracted_reference_min: referenceMin,
    extracted_reference_max: referenceMax,
    measured_at: row.measuredAt || null,
  };
}

export default function MockAnalysisPage() {
  const navigate = useNavigate();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [manualReportDate, setManualReportDate] = useState(todayValue());
  const [manualRows, setManualRows] = useState<ManualRow[]>([
    createManualRow(),
  ]);
  const [backendResult, setBackendResult] =
    useState<LabAnalysisResponse | null>(null);
  const [backendError, setBackendError] = useState('');
  const [isBackendRunning, setIsBackendRunning] = useState(false);
  const [isPdfUploading, setIsPdfUploading] = useState(false);
  const [isManualSubmitting, setIsManualSubmitting] = useState(false);

  const firstBackendResult = backendResult?.results[0] ?? null;
  const abnormalCount = backendResult ? countAbnormal(backendResult.results) : 0;

  const summaryCards = [
    {
      title: 'Structured values',
      value: backendResult?.counts.total ?? 0,
      helper: 'Values returned by the shared backend analysis pipeline.',
    },
    {
      title: 'Needs review',
      value: backendResult?.counts.needs_review ?? 0,
      helper: 'Values with uncertain mapping, range, or classification.',
    },
    {
      title: 'Low / High signals',
      value: abnormalCount,
      helper: 'Values outside an available reference range.',
    },
    {
      title: 'Normal values',
      value: backendResult?.counts.normal ?? 0,
      helper: 'Values classified as normal by deterministic rules.',
    },
  ];

  function updateManualRow(
    rowId: string,
    field: keyof Omit<ManualRow, 'id'>,
    value: string,
  ) {
    setManualRows((currentRows) =>
      currentRows.map((row) =>
        row.id === rowId ? { ...row, [field]: value } : row,
      ),
    );
  }

  function addManualRow() {
    setManualRows((currentRows) => [...currentRows, createManualRow()]);
  }

  function removeManualRow(rowId: string) {
    setManualRows((currentRows) => {
      if (currentRows.length === 1) {
        return [createManualRow()];
      }

      return currentRows.filter((row) => row.id !== rowId);
    });
  }

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

  async function handleSubmitManualResults() {
    try {
      setIsManualSubmitting(true);
      setBackendError('');

      if (!manualReportDate) {
        throw new Error('Report date is required for manual entry.');
      }

      const values = manualRows.map(toManualValue);
      const result = await submitManualLabResults({
        report_date: manualReportDate,
        values,
      });

      setBackendResult(result);
    } catch (error) {
      setBackendError(
        error instanceof Error
          ? error.message
          : 'Manual result analysis failed.',
      );
    } finally {
      setIsManualSubmitting(false);
    }
  }

  function handleGoToResults() {
    if (backendResult) {
      navigate('/analysis/results');
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-semibold uppercase text-cyan-700">
          Lab Analysis
        </p>

        <h2 className="mt-2 text-3xl font-semibold text-slate-950">
          Lab report analysis workspace
        </h2>

        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          Upload a text-based PDF or enter results manually. Both paths use the
          same alias, reference, rule, trend, and persistence pipeline.
        </p>

        <p className="mt-3 inline-flex rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-800">
          Clinical outputs are structured for physician review and are not a
          diagnosis.
        </p>
      </div>

      <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
        <div className="grid gap-5 xl:grid-cols-2">
          <div className="rounded-xl border border-emerald-200 bg-white p-5">
            <p className="text-sm font-semibold uppercase text-emerald-700">
              PDF upload
            </p>

            <h2 className="mt-1 text-xl font-semibold text-slate-950">
              Upload PDF & analyze
            </h2>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Select a text-based PDF. The backend extracts supported values and
              stores a structured analysis run.
            </p>

            <div className="mt-4 rounded-lg border border-dashed border-emerald-300 bg-emerald-50/40 p-4">
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
                {isPdfUploading
                  ? 'Uploading & analyzing...'
                  : 'Upload & Analyze PDF'}
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-cyan-200 bg-white p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-sm font-semibold uppercase text-cyan-700">
                  Manual entry
                </p>

                <h2 className="mt-1 text-xl font-semibold text-slate-950">
                  Enter lab results manually
                </h2>

                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Add one or more test values. They are validated and sent to
                  the same backend analysis pipeline as uploaded reports.
                </p>
              </div>

              <label className="text-sm font-medium text-slate-700">
                Report date
                <input
                  type="date"
                  value={manualReportDate}
                  onChange={(event) => setManualReportDate(event.target.value)}
                  className="mt-1 block rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-950"
                />
              </label>
            </div>

            <div className="mt-4 space-y-4">
              {manualRows.map((row, index) => (
                <div
                  key={row.id}
                  className="rounded-lg border border-slate-200 bg-slate-50 p-4"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-slate-950">
                      Result {index + 1}
                    </p>

                    <button
                      type="button"
                      onClick={() => removeManualRow(row.id)}
                      className="text-sm font-semibold text-red-600 hover:text-red-700"
                    >
                      Remove
                    </button>
                  </div>

                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <label className="text-sm font-medium text-slate-700 sm:col-span-2">
                      Test name
                      <input
                        type="text"
                        value={row.parameterName}
                        onChange={(event) =>
                          updateManualRow(
                            row.id,
                            'parameterName',
                            event.target.value,
                          )
                        }
                        placeholder="Hemoglobin"
                        className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950"
                      />
                    </label>

                    <label className="text-sm font-medium text-slate-700">
                      Result
                      <input
                        type="text"
                        inputMode="decimal"
                        value={row.value}
                        onChange={(event) =>
                          updateManualRow(row.id, 'value', event.target.value)
                        }
                        placeholder="13.8"
                        className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950"
                      />
                    </label>

                    <label className="text-sm font-medium text-slate-700">
                      Unit
                      <input
                        type="text"
                        value={row.unit}
                        onChange={(event) =>
                          updateManualRow(row.id, 'unit', event.target.value)
                        }
                        placeholder="g/dL"
                        className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950"
                      />
                    </label>

                    <label className="text-sm font-medium text-slate-700">
                      Reference minimum
                      <input
                        type="text"
                        inputMode="decimal"
                        value={row.referenceMin}
                        onChange={(event) =>
                          updateManualRow(
                            row.id,
                            'referenceMin',
                            event.target.value,
                          )
                        }
                        placeholder="12"
                        className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950"
                      />
                    </label>

                    <label className="text-sm font-medium text-slate-700">
                      Reference maximum
                      <input
                        type="text"
                        inputMode="decimal"
                        value={row.referenceMax}
                        onChange={(event) =>
                          updateManualRow(
                            row.id,
                            'referenceMax',
                            event.target.value,
                          )
                        }
                        placeholder="16"
                        className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950"
                      />
                    </label>

                    <label className="text-sm font-medium text-slate-700 sm:col-span-2">
                      Measurement date
                      <input
                        type="date"
                        value={row.measuredAt}
                        onChange={(event) =>
                          updateManualRow(
                            row.id,
                            'measuredAt',
                            event.target.value,
                          )
                        }
                        className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950"
                      />
                    </label>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={addManualRow}
                className="rounded-lg border border-cyan-300 bg-white px-4 py-2 text-sm font-semibold text-cyan-800 transition hover:bg-cyan-50"
              >
                + Add Result
              </button>

              <button
                type="button"
                onClick={handleSubmitManualResults}
                disabled={isManualSubmitting}
                className="rounded-lg bg-cyan-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-cyan-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isManualSubmitting
                  ? 'Saving & analyzing...'
                  : 'Save & Analyze Manual Results'}
              </button>
            </div>
          </div>
        </div>

        <div className="mt-5 rounded-xl border border-slate-200 bg-white p-5">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase text-slate-500">
                Controlled backend sample
              </p>
              <h3 className="mt-1 text-lg font-semibold text-slate-950">
                Run demo Hemoglobin payload
              </h3>
              <p className="mt-2 text-sm text-slate-600">
                Keeps the existing fixed sample available for quick backend
                verification.
              </p>
            </div>

            <button
              type="button"
              onClick={handleRunBackendAnalysis}
              disabled={isBackendRunning}
              className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
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
                <p className="font-semibold text-slate-950">
                  Analysis completed
                </p>
                <p className="mt-1 text-slate-600">
                  The latest run is saved and available across the review
                  workflow.
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
                    <p className="mt-1 text-slate-600">
                      Reference: {formatReference(firstBackendResult)}
                    </p>
                  </div>
                  <StatusPill status={firstBackendResult.result_status} />
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      <SectionCard
        title="Analysis summary"
        description="Computed from the latest backend response in this browser session."
      >
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {summaryCards.map((card) => (
            <div
              key={card.title}
              className="rounded-lg border border-slate-200 bg-slate-50 p-4"
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
      </SectionCard>

      <SectionCard
        title="Result preview"
        description="Values returned by the shared backend analysis endpoint."
      >
        {!backendResult ? (
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-sm leading-6 text-slate-600">
            Upload a PDF, enter results manually, or run the sample to preview
            structured results here.
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-slate-200">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="bg-slate-50">
                  <tr>
                    {['Marker', 'Value', 'Reference', 'Status', 'Reason'].map(
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

      <SectionCard
        title="Continue the workflow"
        description="The newest PDF, manual, or sample run becomes the active analysis."
      >
        <div className="grid gap-4 md:grid-cols-3">
          {[
            {
              label: 'View Analysis Results',
              description: 'Inspect every structured result and status.',
              to: '/analysis/results',
              disabled: !backendResult,
            },
            {
              label: 'Open Clinical Review Prompts',
              description: 'Create physician-review prompts from abnormal values.',
              to: '/clinical-hypotheses',
              disabled: !backendResult,
            },
            {
              label: 'Open Timeline',
              description: 'See analysis and review events over time.',
              to: '/timeline',
              disabled: false,
            },
          ].map((action) =>
            action.disabled ? (
              <div
                key={action.label}
                className="cursor-not-allowed rounded-lg border border-slate-200 bg-slate-50 p-4 opacity-60"
              >
                <p className="font-semibold text-slate-950">{action.label}</p>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  {action.description}
                </p>
              </div>
            ) : (
              <Link
                key={action.label}
                to={action.to}
                className="rounded-lg border border-slate-200 bg-white p-4 transition hover:border-blue-200 hover:bg-blue-50"
              >
                <p className="font-semibold text-slate-950">{action.label}</p>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  {action.description}
                </p>
              </Link>
            ),
          )}
        </div>
      </SectionCard>
    </div>
  );
}
