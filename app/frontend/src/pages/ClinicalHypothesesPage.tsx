import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import EmptyState from '../components/ui/EmptyState';
import ErrorState from '../components/ui/ErrorState';
import LoadingState from '../components/ui/LoadingState';
import SectionCard from '../components/ui/SectionCard';
import {
  createClinicalReviewPrompts,
  getClinicalHypothesesForAnalysisRun,
  type ClinicalHypothesis,
} from '../services/clinicalHypothesesClient';

function statusLabel(status: string | null | undefined) {
  return (status ?? 'pending').replace(/_/g, ' ').toUpperCase();
}

function statusClassName(status: string | null | undefined) {
  const normalizedStatus = (status ?? '').toLowerCase();

  if (normalizedStatus.includes('approved')) {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }

  if (normalizedStatus.includes('rejected')) {
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

function severityClassName(severity: string | null) {
  if (severity === 'high') {
    return 'border-rose-200 bg-rose-50 text-rose-700';
  }

  if (severity === 'medium') {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }

  return 'border-slate-200 bg-slate-50 text-slate-700';
}

function formatDate(value: string) {
  try {
    return new Intl.DateTimeFormat('tr-TR', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatConfidence(confidence: number | null) {
  if (confidence === null) {
    return '-';
  }

  return `${Math.round(confidence * 100)}%`;
}

function getPendingCount(prompts: ClinicalHypothesis[]) {
  return prompts.filter((item) =>
    item.status.toLowerCase().includes('pending'),
  ).length;
}

function getEvidenceLinkedCount(prompts: ClinicalHypothesis[]) {
  return prompts.filter((item) => item.evidence_json.length > 0).length;
}

function getNeedsDoctorReviewCount(prompts: ClinicalHypothesis[]) {
  return prompts.filter((item) => item.needs_doctor_review).length;
}

function getPriorityPromptCount(prompts: ClinicalHypothesis[]) {
  return prompts.filter((item) =>
    item.evidence_json.some(
      (evidence) =>
        evidence.result_status === 'low' || evidence.result_status === 'high',
    ),
  ).length;
}

export default function ClinicalHypothesesPage() {
  const [prompts, setPrompts] = useState<ClinicalHypothesis[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const analysisRunId = localStorage.getItem('medicore:lastAnalysisRunId');
  const labReportId = localStorage.getItem('medicore:lastLabReportId');

  async function loadPrompts() {
    try {
      setIsLoading(true);
      setError('');

      if (!analysisRunId) {
        setPrompts([]);
        return;
      }

      const data = await getClinicalHypothesesForAnalysisRun(analysisRunId);
      setPrompts(data);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : 'Unable to load clinical review prompts.',
      );
    } finally {
      setIsLoading(false);
    }
  }

  async function handleCreateReviewPrompts() {
    try {
      setIsCreating(true);
      setError('');
      setMessage('');

      if (!analysisRunId) {
        throw new Error('Upload or run an analysis first.');
      }

      const createdOrExistingPrompts = await createClinicalReviewPrompts(
        analysisRunId,
        labReportId,
      );

      const data = await getClinicalHypothesesForAnalysisRun(analysisRunId);
      setPrompts(data);

      setMessage(
        `${createdOrExistingPrompts.length} clinical review prompt${
          createdOrExistingPrompts.length === 1 ? ' is' : 's are'
        } ready for physician review.`,
      );
    } catch (createError) {
      setError(
        createError instanceof Error
          ? createError.message
          : 'Unable to create clinical review prompts.',
      );
    } finally {
      setIsCreating(false);
    }
  }

  useEffect(() => {
    loadPrompts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisRunId]);

  if (isLoading) {
    return (
      <LoadingState
        title="Loading clinical review prompts"
        description="Fetching review prompts from the backend."
      />
    );
  }

  if (!analysisRunId) {
    return (
      <EmptyState
        title="No analysis run found"
        description="Upload or run an analysis first, then return here to create clinical review prompts."
        actionLabel="Open lab analysis"
        to="/analysis/mock"
      />
    );
  }

  const pendingCount = getPendingCount(prompts);
  const evidenceLinkedCount = getEvidenceLinkedCount(prompts);
  const needsDoctorReviewCount = getNeedsDoctorReviewCount(prompts);
  const priorityPromptCount = getPriorityPromptCount(prompts);

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-semibold uppercase text-cyan-700">
          Clinical Review Prompts
        </p>

        <h2 className="mt-2 text-3xl font-semibold text-slate-950">
          Clinical review prompts
        </h2>

        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          Backend-connected physician review workspace for structured lab
          signal prompts, evidence links, and doctor-review actions.
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

      <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase text-emerald-700">
              Backend connected
            </p>

            <h2 className="mt-1 text-xl font-semibold text-slate-950">
              Create clinical review prompts
            </h2>

            <p className="mt-2 text-sm text-slate-600">
              Creates one physician-review prompt for each LOW or HIGH lab
              signal. Prompts stay blocked from patient-facing use until a
              physician reviews them.
            </p>
          </div>

          <button
            type="button"
            onClick={handleCreateReviewPrompts}
            disabled={isCreating}
            className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isCreating ? 'Creating...' : 'Create Review Prompts'}
          </button>
        </div>

        {message && (
          <div className="mt-4 rounded-lg border border-emerald-200 bg-white px-4 py-3 text-sm text-emerald-700">
            {message}
          </div>
        )}

        {error && (
          <div className="mt-4">
            <ErrorState
              title="Clinical review prompt error"
              description={error}
            />
          </div>
        )}
      </section>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-slate-600">
            Total review prompts
          </p>
          <p className="mt-3 text-3xl font-semibold text-slate-950">
            {prompts.length}
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Backend clinical review prompts
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-slate-600">
            Pending doctor review
          </p>
          <p className="mt-3 text-3xl font-semibold text-slate-950">
            {pendingCount}
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Prompts waiting for physician action
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-slate-600">
            Priority lab prompts
          </p>
          <p className="mt-3 text-3xl font-semibold text-slate-950">
            {priorityPromptCount}
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            LOW or HIGH lab signals converted into review prompts
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-medium text-slate-600">
            Evidence-linked prompts
          </p>
          <p className="mt-3 text-3xl font-semibold text-slate-950">
            {evidenceLinkedCount}
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Connected to structured lab result signals
          </p>
        </div>
      </div>

      <SectionCard
        title="Review prompt queue"
        description="Review prompts only. These are not diagnoses or treatment recommendations."
      >
        {prompts.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-6">
            <h3 className="font-semibold text-slate-950">
              No clinical review prompts yet
            </h3>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Create review prompts from LOW or HIGH backend lab signals.
            </p>

            <button
              type="button"
              onClick={handleCreateReviewPrompts}
              disabled={isCreating}
              className="mt-4 rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isCreating ? 'Creating...' : 'Create Review Prompts'}
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {prompts.map((item) => (
              <article
                key={item.id}
                className="rounded-lg border border-slate-200 bg-slate-50 p-5"
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-slate-950">
                      {item.title}
                    </h3>

                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      {item.summary}
                    </p>
                  </div>

                  <div className="flex flex-wrap gap-2 lg:justify-end">
                    <span
                      className={`whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                        item.status,
                      )}`}
                    >
                      {statusLabel(item.status)}
                    </span>

                    <span
                      className={`whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs font-semibold ${severityClassName(
                        item.severity,
                      )}`}
                    >
                      {(item.severity ?? 'low').toUpperCase()} priority
                    </span>
                  </div>
                </div>

                <div className="mt-5 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
                  <div className="rounded-lg border border-blue-100 bg-white p-4">
                    <p className="text-xs font-semibold uppercase text-blue-700">
                      Review focus
                    </p>

                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      Physician should review the structured lab signal,
                      clinical context, reference range, and whether follow-up
                      is appropriate.
                    </p>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
                    <div className="rounded-lg border border-slate-200 bg-white p-3">
                      <p className="text-xs font-semibold uppercase text-slate-500">
                        Confidence
                      </p>

                      <p className="mt-2 text-sm font-medium text-slate-950">
                        {formatConfidence(item.confidence)}
                      </p>
                    </div>

                    <div className="rounded-lg border border-slate-200 bg-white p-3">
                      <p className="text-xs font-semibold uppercase text-slate-500">
                        Generated
                      </p>

                      <p className="mt-2 text-sm font-medium text-slate-950">
                        {formatDate(item.created_at)}
                      </p>
                    </div>

                    <div className="rounded-lg border border-slate-200 bg-white p-3">
                      <p className="text-xs font-semibold uppercase text-slate-500">
                        Source
                      </p>

                      <p className="mt-2 text-sm font-medium text-slate-950">
                        {item.source}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {item.evidence_json.length === 0 ? (
                    <span className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600">
                      No evidence attached
                    </span>
                  ) : (
                    item.evidence_json.map((evidence, index) => (
                      <span
                        key={`${item.id}-${index}`}
                        className="rounded-lg border border-cyan-100 bg-cyan-50 px-2.5 py-1 text-xs font-semibold text-cyan-700"
                      >
                        {evidence.parameter_name ?? evidence.parameter_code}:{' '}
                        {evidence.value} {evidence.unit} ·{' '}
                        {statusLabel(evidence.result_status)}
                      </span>
                    ))
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Evidence signal cards"
        description="Evidence-linked lab signals for physician review prompts."
      >
        {prompts.length === 0 ? (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
            No evidence signals yet. Create review prompts first.
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {prompts.flatMap((item) =>
              item.evidence_json.map((evidence, index) => (
                <article
                  key={`${item.id}-evidence-${index}`}
                  className="rounded-lg border border-slate-200 bg-slate-50 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="font-semibold text-slate-950">
                        {evidence.parameter_name ??
                          evidence.parameter_code ??
                          'Lab signal'}
                      </h3>

                      <p className="mt-2 text-sm text-slate-600">
                        {evidence.value} {evidence.unit}
                      </p>
                    </div>

                    <span
                      className={`whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                        evidence.result_status,
                      )}`}
                    >
                      {statusLabel(evidence.result_status)}
                    </span>
                  </div>

                  <p className="mt-4 text-sm font-medium text-slate-700">
                    Related prompt: {item.title}
                  </p>

                  <p className="mt-3 rounded-lg border border-blue-100 bg-white p-3 text-sm leading-6 text-slate-600">
                    {evidence.note ??
                      'Structured evidence signal prepared for physician review.'}
                  </p>
                </article>
              )),
            )}
          </div>
        )}
      </SectionCard>

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <SectionCard
          title="Safe navigation"
          description="Links to related backend-connected review workspaces."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Link
              to="/analysis/results"
              className="rounded-lg border border-slate-200 bg-slate-50 p-4 transition hover:border-blue-200 hover:bg-blue-50"
            >
              <p className="font-semibold text-slate-950">
                View analysis results
              </p>

              <p className="mt-2 text-sm leading-6 text-slate-600">
                Review structured backend lab result rows.
              </p>
            </Link>

            <Link
              to="/doctor-review"
              className="rounded-lg border border-slate-200 bg-slate-50 p-4 transition hover:border-blue-200 hover:bg-blue-50"
            >
              <p className="font-semibold text-slate-950">
                Open doctor review
              </p>

              <p className="mt-2 text-sm leading-6 text-slate-600">
                Continue with physician approval controls.
              </p>
            </Link>
          </div>
        </SectionCard>

        <SectionCard
          title="Safety framing"
          description="Review prompts stay blocked from patient-facing use until approved."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-blue-100 bg-blue-50 p-4 text-sm leading-6 text-slate-700">
              Prompts are review prompts, not diagnoses.
            </div>

            <div className="rounded-lg border border-cyan-100 bg-cyan-50 p-4 text-sm leading-6 text-slate-700">
              Evidence comes from deterministic lab result labels.
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-700">
              LOW/HIGH signals are routed to physician review.
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-700">
              Final clinical decisions belong to a physician.
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="rounded-lg border border-blue-100 bg-blue-50 p-4 text-sm leading-6 text-blue-800">
        This page creates structured review prompts from backend lab signal
        statuses. It does not provide diagnosis, treatment, or final clinical
        decisions.
      </div>
    </div>
  );
}
 
 
 
 
 
 
 
 
 
 

 
 
 

 
 
 

 
 
 

 
 
 
 
 
 

 
 
 

 
 
 
 

 
 
 
 

 
 
 
 
 

 
 
 
 
 
 

 
 
 

 
 
 
 
 

 
 
 
 
 
 
 
 
 

 
 
 
 
 

 
 
 
 
 
 
 

 
 
 
 
 
 
 
 
 
 
 
 

 
 
 
 
 
 
 
 
 
 
 

 
 
 
 
 
 
 
 
 
 
 

 
 
 
 
 
 
 
 
 
 
 
 

 
 
 
 
 
 
 
 
 

 
 
 

 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 

 
 
 
 

 
 
 
 
 
 
 
 

 
 
 
 
 
 
 
 
 

 
 
 
 
 

 
 
 
 
 

 
 
 
 
 

 
 
 
 

 
 
 
 

 
 
 
 

 
 
 
 

 
 
 
 
 
 

 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 

 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 

 
 
 
 

 
 
 
 
 
 
 
 

 
 
 

 
 
 
 
 
 
 
 
 
 

 
 
 
 
 
 
 
 
 
 
 
 
 

 
 
 
 

 
 
 
 
 
 
 

 
 
 
 
 
 

 
 
 
 
 
 
 
 
 
 

 
 
 
 
 

 
 
 
 
 

 
 
 
 
 
 
 
 
 
 
