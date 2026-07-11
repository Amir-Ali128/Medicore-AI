import { useMemo, useState, type ChangeEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import SectionCard from '../components/ui/SectionCard';
import {
  generateClaudeAbnormalReview,
  type ClaudeReviewGenerationResult,
} from '../services/claudeReviewClient';
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

type ManualField = {
  key: keyof Omit<ManualRow, 'id'>;
  label: string;
  placeholder?: string;
  type?: 'text' | 'date';
  inputMode?: 'text' | 'decimal';
  wide?: boolean;
};

type ResultTone = 'low' | 'high' | 'review';

const MANUAL_FIELDS: ManualField[] = [
  {
    key: 'parameterName',
    label: 'Test name',
    placeholder: 'Hemoglobin',
    wide: true,
  },
  {
    key: 'value',
    label: 'Result',
    placeholder: '13.8',
    inputMode: 'decimal',
  },
  { key: 'unit', label: 'Unit', placeholder: 'g/dL' },
  {
    key: 'referenceMin',
    label: 'Reference minimum',
    placeholder: '12',
    inputMode: 'decimal',
  },
  {
    key: 'referenceMax',
    label: 'Reference maximum',
    placeholder: '16',
    inputMode: 'decimal',
  },
  {
    key: 'measuredAt',
    label: 'Measurement date',
    type: 'date',
    wide: true,
  },
];

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
  if (status === 'high') return 'border-red-200 bg-red-50 text-red-700';
  if (status === 'low') return 'border-amber-200 bg-amber-50 text-amber-800';
  return 'border-violet-200 bg-violet-50 text-violet-700';
}

function StatusPill({ status }: { status: LabResultStatus | string }) {
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${statusClassName(
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
    result.unit ?? ''
  }`;
}

function parseOptionalNumber(value: string): number | null {
  if (!value.trim()) return null;

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

function ResultGroup({
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

  const border =
    tone === 'high'
      ? 'border-red-200'
      : tone === 'low'
        ? 'border-amber-200'
        : 'border-violet-200';
  const header =
    tone === 'high'
      ? 'bg-red-50 text-red-800'
      : tone === 'low'
        ? 'bg-amber-50 text-amber-800'
        : 'bg-violet-50 text-violet-800';

  return (
    <section className={`overflow-hidden rounded-xl border ${border}`}>
      <div
        className={`flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between ${header}`}
      >
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
            {results.map((result) => (
              <tr key={result.lab_result_id}>
                <td className="px-4 py-4 font-medium text-slate-950">
                  {result.canonical_name ?? result.raw_parameter_name}
                </td>
                <td className="whitespace-nowrap px-4 py-4 text-slate-700">
                  {result.normalized_value} {result.unit}
                </td>
                <td className="whitespace-nowrap px-4 py-4 text-slate-600">
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
    </section>
  );
}

export default function MockAnalysisPage() {
  const navigate = useNavigate();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [manualReportDate, setManualReportDate] = useState(todayValue());
  const [chiefComplaint, setChiefComplaint] = useState('');
  const [clinicalHistory, setClinicalHistory] = useState('');
  const [manualRows, setManualRows] = useState<ManualRow[]>([
    createManualRow(),
  ]);
  const [backendResult, setBackendResult] =
    useState<LabAnalysisResponse | null>(null);
  const [backendError, setBackendError] = useState('');
  const [busyAction, setBusyAction] = useState<
    'sample' | 'pdf' | 'manual' | null
  >(null);
  const [isClaudeGenerating, setIsClaudeGenerating] = useState(false);
  const [claudeResult, setClaudeResult] =
    useState<ClaudeReviewGenerationResult | null>(null);
  const [claudeError, setClaudeError] = useState('');

  const groupedResults = useMemo(() => {
    const results = backendResult?.results ?? [];

    return {
      high: results.filter((item) => item.result_status === 'high'),
      low: results.filter((item) => item.result_status === 'low'),
      review: results.filter(
        (item) =>
          item.result_status === 'needs_review' ||
          item.result_status === 'unknown',
      ),
    };
  }, [backendResult]);

  const visibleResults = useMemo(
    () => [
      ...groupedResults.high,
      ...groupedResults.low,
      ...groupedResults.review,
    ],
    [groupedResults],
  );

  const summaryCards = [
    [
      'Processed results',
      backendResult?.counts.total ?? 0,
      'All values processed by the deterministic pipeline.',
    ],
    [
      'High signals',
      groupedResults.high.length,
      'Above an available reference range.',
    ],
    [
      'Low signals',
      groupedResults.low.length,
      'Below an available reference range.',
    ],
    [
      'Needs review',
      groupedResults.review.length,
      'Unknown or uncertain results separated for review.',
    ],
  ] as const;

  function acceptResult(result: LabAnalysisResponse) {
    setBackendResult(result);
    setClaudeResult(null);
    setClaudeError('');
  }

  function updateManualRow(
    rowId: string,
    field: keyof Omit<ManualRow, 'id'>,
    value: string,
  ) {
    setManualRows((rows) =>
      rows.map((row) => (row.id === rowId ? { ...row, [field]: value } : row)),
    );
  }

  function removeManualRow(rowId: string) {
    setManualRows((rows) =>
      rows.length === 1
        ? [createManualRow()]
        : rows.filter((row) => row.id !== rowId),
    );
  }

  async function runAction(action: 'sample' | 'pdf' | 'manual') {
    try {
      setBusyAction(action);
      setBackendError('');

      if (action === 'sample') {
        acceptResult(await runBackendMockAnalysis());
      } else if (action === 'pdf') {
        if (!selectedFile) {
          throw new Error('Please choose a PDF file first.');
        }

        acceptResult(await uploadLabReportPdf(selectedFile));
      } else {
        if (!manualReportDate) {
          throw new Error('Report date is required for manual entry.');
        }

        acceptResult(
          await submitManualLabResults({
            report_date: manualReportDate,
            chief_complaint: chiefComplaint.trim() || null,
            clinical_history: clinicalHistory.trim() || null,
            values: manualRows.map(toManualValue),
          }),
        );
      }
    } catch (error) {
      setBackendError(error instanceof Error ? error.message : 'Analysis failed.');
    } finally {
      setBusyAction(null);
    }
  }

  async function handleGenerateClaudeReview() {
    if (!backendResult || visibleResults.length === 0) return;

    try {
      setIsClaudeGenerating(true);
      setClaudeError('');
      setClaudeResult(
        await generateClaudeAbnormalReview(
          backendResult.analysis_run_id,
          Math.min(visibleResults.length, 5),
          {
            chief_complaint: chiefComplaint.trim() || null,
            clinical_history: clinicalHistory.trim() || null,
          },
        ),
      );
    } catch (error) {
      setClaudeError(
        error instanceof Error ? error.message : 'Claude review failed.',
      );
    } finally {
      setIsClaudeGenerating(false);
    }
  }

  return (
    <div className="space-y-8">
      <header>
        <p className="text-sm font-semibold uppercase text-cyan-700">
          Lab Analysis
        </p>
        <h2 className="mt-2 text-3xl font-semibold text-slate-950">
          Lab report analysis workspace
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          Upload a text-based PDF or enter results manually. Normal values are
          processed but hidden from this review screen; abnormal and uncertain
          values are separated below.
        </p>
        <p className="mt-3 inline-flex rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-800">
          Claude output is for physician review only and is not a diagnosis or
          treatment recommendation.
        </p>
      </header>

      <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
        <div className="grid gap-5 xl:grid-cols-2">
          <div className="rounded-xl border border-emerald-200 bg-white p-5">
            <p className="text-sm font-semibold uppercase text-emerald-700">
              PDF upload
            </p>
            <h3 className="mt-1 text-xl font-semibold text-slate-950">
              Upload PDF & analyze
            </h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              The backend extracts supported values and stores a structured
              analysis run.
            </p>
            <div className="mt-4 rounded-lg border border-dashed border-emerald-300 bg-emerald-50/40 p-4">
              <input
                type="file"
                accept="application/pdf,.pdf"
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  setSelectedFile(event.target.files?.[0] ?? null)
                }
                className="block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-slate-950 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-slate-800"
              />
              {selectedFile && (
                <p className="mt-3 text-sm text-slate-600">
                  Selected:{' '}
                  <strong className="text-slate-950">{selectedFile.name}</strong>
                </p>
              )}
              <button
                type="button"
                onClick={() => runAction('pdf')}
                disabled={busyAction !== null || !selectedFile}
                className="mt-4 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === 'pdf'
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
                <h3 className="mt-1 text-xl font-semibold text-slate-950">
                  Enter lab results manually
                </h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Manual values, complaint, and history are stored with the same
                  analysis report.
                </p>
              </div>
              <label className="text-sm font-medium text-slate-700">
                Report date
                <input
                  type="date"
                  value={manualReportDate}
                  onChange={(event: ChangeEvent<HTMLInputElement>) =>
                    setManualReportDate(event.target.value)
                  }
                  className="mt-1 block rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-950"
                />
              </label>
            </div>

            <div className="mt-5 rounded-lg border border-cyan-200 bg-cyan-50/50 p-4">
              <div>
                <p className="text-sm font-semibold text-slate-950">
                  Klinik bilgiler
                </p>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  Bu alanlar isteğe bağlıdır ve doktor değerlendirmesi için analiz
                  kaydına eklenir.
                </p>
              </div>

              <div className="mt-4 grid gap-4">
                <label className="text-sm font-medium text-slate-700">
                  Şikayet
                  <textarea
                    value={chiefComplaint}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
                      setChiefComplaint(event.target.value)
                    }
                    maxLength={2000}
                    rows={3}
                    placeholder="Örn: Halsizlik, baş dönmesi ve çabuk yorulma..."
                    className="mt-1 block w-full resize-y rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm leading-6 text-slate-950 placeholder:text-slate-400"
                  />
                  <span className="mt-1 block text-right text-xs text-slate-400">
                    {chiefComplaint.length}/2000
                  </span>
                </label>

                <label className="text-sm font-medium text-slate-700">
                  Öykü
                  <textarea
                    value={clinicalHistory}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
                      setClinicalHistory(event.target.value)
                    }
                    maxLength={5000}
                    rows={5}
                    placeholder="Örn: Şikayetlerin başlangıcı, süresi, bilinen hastalıklar, kullanılan ilaçlar ve önceki tetkikler..."
                    className="mt-1 block w-full resize-y rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm leading-6 text-slate-950 placeholder:text-slate-400"
                  />
                  <span className="mt-1 block text-right text-xs text-slate-400">
                    {clinicalHistory.length}/5000
                  </span>
                </label>
              </div>
            </div>

            <div className="mt-4 max-h-[34rem] space-y-4 overflow-y-auto pr-1">
              {manualRows.map((row, index) => (
                <div
                  key={row.id}
                  className="rounded-lg border border-slate-200 bg-slate-50 p-4"
                >
                  <div className="flex items-center justify-between">
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
                    {MANUAL_FIELDS.map((field) => (
                      <label
                        key={field.key}
                        className={`text-sm font-medium text-slate-700 ${
                          field.wide ? 'sm:col-span-2' : ''
                        }`}
                      >
                        {field.label}
                        <input
                          type={field.type ?? 'text'}
                          inputMode={field.inputMode}
                          value={row[field.key]}
                          placeholder={field.placeholder}
                          onChange={(event: ChangeEvent<HTMLInputElement>) =>
                            updateManualRow(
                              row.id,
                              field.key,
                              event.target.value,
                            )
                          }
                          className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950"
                        />
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() =>
                  setManualRows((rows) => [...rows, createManualRow()])
                }
                className="rounded-lg border border-cyan-300 bg-white px-4 py-2 text-sm font-semibold text-cyan-800 hover:bg-cyan-50"
              >
                + Add Result
              </button>
              <button
                type="button"
                onClick={() => runAction('manual')}
                disabled={busyAction !== null}
                className="rounded-lg bg-cyan-700 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === 'manual'
                  ? 'Saving & analyzing...'
                  : 'Save & Analyze Manual Results'}
              </button>
            </div>
          </div>
        </div>

        <div className="mt-5 flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-5 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase text-slate-500">
              Controlled backend sample
            </p>
            <p className="mt-1 font-semibold text-slate-950">
              Run demo Hemoglobin payload
            </p>
          </div>
          <button
            type="button"
            onClick={() => runAction('sample')}
            disabled={busyAction !== null}
            className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {busyAction === 'sample' ? 'Running...' : 'Run Backend Analysis'}
          </button>
        </div>

        {backendError && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {backendError}
          </div>
        )}

        {backendResult && (
          <div className="mt-4 flex flex-col gap-3 rounded-lg border border-emerald-200 bg-white p-4 text-sm md:flex-row md:items-center md:justify-between">
            <p className="text-slate-600">
              <strong className="text-slate-950">Analysis completed.</strong>{' '}
              {visibleResults.length} non-normal result(s) are visible; normal
              rows are hidden.
              {(chiefComplaint.trim() || clinicalHistory.trim()) && (
                <span className="ml-1 text-cyan-700">
                  Klinik bilgiler analiz kaydına eklendi.
                </span>
              )}
            </p>
            <button
              type="button"
              onClick={() => navigate('/analysis/results')}
              className="rounded-lg bg-blue-700 px-4 py-2 font-semibold text-white hover:bg-blue-800"
            >
              View Full Analysis Record
            </button>
          </div>
        )}
      </section>

      <SectionCard
        title="Analysis summary"
        description="Normal rows are excluded from the visible review queue."
      >
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {summaryCards.map(([title, value, helper]) => (
            <div
              key={title}
              className="rounded-lg border border-slate-200 bg-slate-50 p-4"
            >
              <p className="text-sm font-medium text-slate-600">{title}</p>
              <p className="mt-3 text-3xl font-semibold text-slate-950">
                {value}
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                {helper}
              </p>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Abnormal and review-required results"
        description="HIGH, LOW, NEEDS REVIEW, and UNKNOWN values are separated. Normal values are intentionally hidden."
      >
        {!backendResult ? (
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
            Complete an analysis to build the review queue.
          </div>
        ) : visibleResults.length === 0 ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-6 text-sm text-emerald-800">
            No abnormal or review-required result was found. Normal rows remain
            hidden by design.
          </div>
        ) : (
          <div className="space-y-5">
            <ResultGroup
              title="High results"
              description="Above the available reference range."
              results={groupedResults.high}
              tone="high"
            />
            <ResultGroup
              title="Low results"
              description="Below the available reference range."
              results={groupedResults.low}
              tone="low"
            />
            <ResultGroup
              title="Needs review"
              description="Uncertain mapping, range, or classification."
              results={groupedResults.review}
              tone="review"
            />
          </div>
        )}
      </SectionCard>

      <section className="rounded-xl border border-violet-200 bg-violet-50 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase text-violet-700">
              Claude clinical copilot
            </p>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">
              Generate an abnormal-result review
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              Only non-normal structured results are sent to Claude. Entered
              complaint and history are attached as physician-review context.
            </p>
          </div>
          <button
            type="button"
            onClick={handleGenerateClaudeReview}
            disabled={
              !backendResult ||
              visibleResults.length === 0 ||
              isClaudeGenerating
            }
            className="rounded-lg bg-violet-700 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isClaudeGenerating
              ? 'Generating Claude review...'
              : 'Generate Claude Review'}
          </button>
        </div>

        {!backendResult && (
          <p className="mt-4 text-sm text-slate-600">
            Complete an analysis before generating a Claude review.
          </p>
        )}
        {backendResult && visibleResults.length === 0 && (
          <p className="mt-4 text-sm text-slate-600">
            Claude review is disabled because there are no non-normal results.
          </p>
        )}
        {claudeError && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {claudeError}
          </div>
        )}

        {claudeResult && (
          <div className="mt-5 space-y-4">
            <div className="rounded-lg border border-violet-200 bg-white p-4 text-sm text-slate-700">
              Claude created {claudeResult.created_count} physician-review
              hypothesis/hypotheses.
            </div>
            {claudeResult.created_hypotheses.map((hypothesis) => (
              <article
                key={hypothesis.id}
                className="rounded-xl border border-violet-200 bg-white p-5"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h3 className="font-semibold text-slate-950">
                      {hypothesis.title}
                    </h3>
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      {hypothesis.summary}
                    </p>
                  </div>
                  <span className="whitespace-nowrap rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-semibold text-violet-700">
                    PHYSICIAN REVIEW
                  </span>
                </div>
                {hypothesis.confidence !== null && (
                  <p className="mt-3 text-xs font-medium text-slate-500">
                    Model confidence:{' '}
                    {Math.round(hypothesis.confidence * 100)}%
                  </p>
                )}
              </article>
            ))}
            {claudeResult.created_hypotheses.length === 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                Claude did not return a hypothesis that passed the safety and
                evidence checks.
              </div>
            )}
            {claudeResult.warnings.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                <p className="text-sm font-semibold text-amber-900">Warnings</p>
                <ul className="mt-2 space-y-1 text-sm text-amber-800">
                  {claudeResult.warnings.map((warning) => (
                    <li key={warning}>• {warning}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      <SectionCard
        title="Continue the workflow"
        description="Open the persisted analysis and physician-review queues."
      >
        <div className="grid gap-4 md:grid-cols-3">
          {[
            [
              'View Analysis Results',
              'Open the complete stored analysis record.',
              '/analysis/results',
              !backendResult,
            ],
            [
              'Open Clinical Review Prompts',
              'Review Claude and structured physician prompts.',
              '/clinical-hypotheses',
              !backendResult,
            ],
            [
              'Open Timeline',
              'See analysis and review events over time.',
              '/timeline',
              false,
            ],
          ].map(([label, description, to, disabled]) =>
            disabled ? (
              <div
                key={String(label)}
                className="cursor-not-allowed rounded-lg border border-slate-200 bg-slate-50 p-4 opacity-60"
              >
                <p className="font-semibold text-slate-950">{label}</p>
                <p className="mt-2 text-sm text-slate-500">{description}</p>
              </div>
            ) : (
              <Link
                key={String(label)}
                to={String(to)}
                className="rounded-lg border border-slate-200 bg-white p-4 hover:border-blue-200 hover:bg-blue-50"
              >
                <p className="font-semibold text-slate-950">{label}</p>
                <p className="mt-2 text-sm text-slate-500">{description}</p>
              </Link>
            ),
          )}
        </div>
      </SectionCard>
    </div>
  );
}
