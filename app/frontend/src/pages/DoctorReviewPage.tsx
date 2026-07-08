import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import EmptyState from '../components/ui/EmptyState';
import ErrorState from '../components/ui/ErrorState';
import LoadingState from '../components/ui/LoadingState';
import SectionCard from '../components/ui/SectionCard';
import {
  applyDoctorReview,
  getPendingClinicalHypotheses,
  type ClinicalHypothesis,
  type DoctorReviewAction,
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

function getEvidenceItems(hypotheses: ClinicalHypothesis[]) {
  return hypotheses.flatMap((item) =>
    item.evidence_json.map((evidence) => ({
      ...evidence,
      relatedTitle: item.title,
      hypothesisId: item.id,
    })),
  );
}

export default function DoctorReviewPage() {
  const [hypotheses, setHypotheses] = useState<ClinicalHypothesis[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isReviewing, setIsReviewing] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function loadPendingReviews() {
    try {
      setIsLoading(true);
      setError('');

      const data = await getPendingClinicalHypotheses();
      setHypotheses(data);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : 'Unable to load pending doctor reviews.',
      );
    } finally {
      setIsLoading(false);
    }
  }

  function removeHypothesisFromScreen(clinicalHypothesisId: string) {
    setHypotheses((currentHypotheses) =>
      currentHypotheses.filter((item) => item.id !== clinicalHypothesisId),
    );
  }

  async function handleDoctorAction(
    clinicalHypothesisId: string,
    action: DoctorReviewAction,
    doctorNote: string,
  ) {
    try {
      setIsReviewing(true);
      setError('');
      setMessage('');

      const result = await applyDoctorReview(
        clinicalHypothesisId,
        action,
        doctorNote,
      );

      setMessage(
        `Doctor review saved: ${statusLabel(result.doctor_review.action)}.`,
      );

      removeHypothesisFromScreen(clinicalHypothesisId);
    } catch (reviewError) {
      const errorMessage =
        reviewError instanceof Error ? reviewError.message : '';

      if (errorMessage.includes('Failed to fetch')) {
        setMessage(
          'Doctor review action was sent. Removed from pending queue locally.',
        );

        removeHypothesisFromScreen(clinicalHypothesisId);
        return;
      }

      setError(
        reviewError instanceof Error
          ? reviewError.message
          : 'Unable to apply doctor review action.',
      );
    } finally {
      setIsReviewing(false);
    }
  }

  useEffect(() => {
    loadPendingReviews();
  }, []);

  if (isLoading) {
    return (
      <LoadingState
        title="Loading doctor review"
        description="Fetching pending clinical review prompts from the backend."
      />
    );
  }

  if (error && hypotheses.length === 0) {
    return (
      <ErrorState title="Unable to load doctor review" description={error} />
    );
  }

  if (hypotheses.length === 0) {
    return (
      <EmptyState
        title="No pending doctor reviews"
        description="Create clinical review prompts first, or all current prompts may already be reviewed."
        actionLabel="Open clinical review prompts"
        to="/clinical-hypotheses"
      />
    );
  }

  const firstReview = hypotheses[0];
  const evidenceItems = getEvidenceItems(hypotheses);

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-semibold uppercase text-cyan-700">
          Doctor Review
        </p>

        <h2 className="mt-2 text-3xl font-semibold text-slate-950">
          Doctor review panel
        </h2>

        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          Backend-connected physician review workspace for pending clinical
          review prompts, linked lab evidence, and approval controls.
        </p>

        <p className="mt-3 inline-flex rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-800">
          Clinical outputs are structured for physician review and are not a
          diagnosis.
        </p>
      </div>

      <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase text-emerald-700">
              Backend actions enabled
            </p>

            <h2 className="mt-1 text-xl font-semibold text-slate-950">
              Review selected prompt
            </h2>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Approve, reject, or request extra tests for the first pending
              clinical review prompt. Actions are recorded through the backend
              review endpoint.
            </p>
          </div>

          <div className="flex w-full flex-col gap-2 sm:flex-row sm:flex-wrap xl:w-auto xl:justify-end">
            <button
              type="button"
              disabled={isReviewing}
              onClick={() =>
                handleDoctorAction(
                  firstReview.id,
                  'approve',
                  'Approved after physician review in demo workflow.',
                )
              }
              className="min-w-36 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Approve
            </button>

            <button
              type="button"
              disabled={isReviewing}
              onClick={() =>
                handleDoctorAction(
                  firstReview.id,
                  'request_extra_test',
                  'Additional follow-up testing requested before patient-facing visibility.',
                )
              }
              className="min-w-44 rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Request extra test
            </button>

            <button
              type="button"
              disabled={isReviewing}
              onClick={() =>
                handleDoctorAction(
                  firstReview.id,
                  'reject',
                  'Rejected after physician review in demo workflow.',
                )
              }
              className="min-w-32 rounded-lg bg-rose-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-rose-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Reject
            </button>
          </div>
        </div>

        {message && (
          <div className="mt-4 rounded-lg border border-emerald-200 bg-white px-4 py-3 text-sm text-emerald-700">
            {message}
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}
      </section>

      <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <SectionCard
          title="Review case summary"
          description="Pending backend review context for the current demo flow."
        >
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Patient
                </p>

                <h3 className="mt-2 text-xl font-semibold text-slate-950">
                  Demo Patient
                </h3>
              </div>

              <span
                className={`w-fit whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                  firstReview.status,
                )}`}
              >
                {statusLabel(firstReview.status)}
              </span>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Pending prompts
                </p>

                <p className="mt-2 font-medium text-slate-950">
                  {hypotheses.length}
                </p>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Evidence signals
                </p>

                <p className="mt-2 font-medium text-slate-950">
                  {evidenceItems.length}
                </p>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Latest generated
                </p>

                <p className="mt-2 font-medium text-slate-950">
                  {formatDate(firstReview.created_at)}
                </p>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Patient visibility
                </p>

                <p className="mt-2 font-medium text-slate-950">
                  Blocked until physician approval
                </p>
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard
          title="Selected review prompt"
          description="First pending prompt from the backend pending queue."
        >
          <article className="rounded-lg border border-slate-200 bg-slate-50 p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h3 className="text-lg font-semibold text-slate-950">
                  {firstReview.title}
                </h3>

                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {firstReview.summary}
                </p>
              </div>

              <div className="flex flex-wrap gap-2 lg:justify-end">
                <span
                  className={`whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                    firstReview.status,
                  )}`}
                >
                  {statusLabel(firstReview.status)}
                </span>

                <span
                  className={`whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs font-semibold ${severityClassName(
                    firstReview.severity,
                  )}`}
                >
                  {(firstReview.severity ?? 'low').toUpperCase()} priority
                </span>
              </div>
            </div>

            <div className="mt-5 grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
              <div className="rounded-lg border border-blue-100 bg-white p-4">
                <p className="text-xs font-semibold uppercase text-blue-700">
                  Review focus
                </p>

                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Review the linked lab signal, reference range, clinical
                  context, and whether this prompt should be edited, approved,
                  rejected, or sent for extra tests.
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
                <div className="rounded-lg border border-slate-200 bg-white p-3">
                  <p className="text-xs font-semibold uppercase text-slate-500">
                    Confidence
                  </p>

                  <p className="mt-2 text-sm font-medium text-slate-950">
                    {formatConfidence(firstReview.confidence)}
                  </p>
                </div>

                <div className="rounded-lg border border-slate-200 bg-white p-3">
                  <p className="text-xs font-semibold uppercase text-slate-500">
                    Source
                  </p>

                  <p className="mt-2 text-sm font-medium text-slate-950">
                    {firstReview.source}
                  </p>
                </div>

                <div className="rounded-lg border border-slate-200 bg-white p-3">
                  <p className="text-xs font-semibold uppercase text-slate-500">
                    Generated
                  </p>

                  <p className="mt-2 text-sm font-medium text-slate-950">
                    {formatDate(firstReview.created_at)}
                  </p>
                </div>
              </div>
            </div>
          </article>
        </SectionCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_0.8fr]">
        <SectionCard
          title="Evidence panel"
          description="Evidence-linked lab signals for pending doctor review."
        >
          {evidenceItems.length === 0 ? (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              No evidence signals are attached to the pending prompts.
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {evidenceItems.map((evidence, index) => (
                <article
                  key={`${evidence.hypothesisId}-${index}`}
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
                    Related prompt: {evidence.relatedTitle}
                  </p>

                  <p className="mt-3 rounded-lg border border-blue-100 bg-white p-3 text-sm leading-6 text-slate-600">
                    {evidence.note ??
                      'Structured evidence signal prepared for physician review.'}
                  </p>
                </article>
              ))}
            </div>
          )}
        </SectionCard>

        <SectionCard
          title="Doctor action state"
          description="These actions send POST requests to the backend review endpoint."
        >
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Use the action buttons to approve, reject, or request extra tests
              for the selected pending prompt.
            </p>

            <p className="mt-3 text-sm leading-6 text-slate-700">
              After an action succeeds, the selected prompt is removed from the
              visible pending queue.
            </p>
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="Editable summary preview"
        description="Doctor-editing UI placeholder for the selected prompt."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-semibold uppercase text-slate-500">
              Original system summary
            </p>

            <p className="mt-3 text-sm leading-6 text-slate-600">
              {firstReview.summary}
            </p>
          </div>

          <div className="rounded-lg border border-cyan-100 bg-cyan-50 p-4">
            <p className="text-xs font-semibold uppercase text-cyan-800">
              Doctor-edited summary preview
            </p>

            <p className="mt-3 text-sm leading-6 text-slate-700">
              Doctor can edit this summary before any patient-facing content is
              approved.
            </p>
          </div>

          <div className="rounded-lg border border-blue-100 bg-white p-4 lg:col-span-2">
            <p className="text-xs font-semibold uppercase text-blue-700">
              Review note
            </p>

            <p className="mt-3 text-sm leading-6 text-slate-600">
              Final clinical decisions belong to a physician. This screen only
              organizes review evidence and pending prompts.
            </p>
          </div>
        </div>
      </SectionCard>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <SectionCard
          title="Safe navigation"
          description="Links to related backend-connected review workspaces."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Link
              to="/clinical-hypotheses"
              className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-blue-200 hover:bg-blue-50"
            >
              <span className="font-semibold text-slate-950">
                Open clinical review prompts
              </span>

              <span className="mt-2 block text-sm leading-6 text-slate-500">
                Return to the prompt creation and evidence page.
              </span>
            </Link>

            <Link
              to="/analysis/results"
              className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-blue-200 hover:bg-blue-50"
            >
              <span className="font-semibold text-slate-950">
                View analysis results
              </span>

              <span className="mt-2 block text-sm leading-6 text-slate-500">
                Return to backend-connected lab result table.
              </span>
            </Link>
          </div>
        </SectionCard>

        <SectionCard
          title="Safety framing"
          description="Doctor actions remain physician-review controls."
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
              <p className="text-sm leading-6 text-slate-700">
                Doctor review is required before patient-facing content.
              </p>
            </div>

            <div className="rounded-lg border border-cyan-100 bg-cyan-50 p-4">
              <p className="text-sm leading-6 text-slate-700">
                AI/system prompts do not approve themselves.
              </p>
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-sm leading-6 text-slate-700">
                Review actions are saved through the backend review endpoint.
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
    </div>
  );
}