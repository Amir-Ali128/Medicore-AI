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

function statusLabel(status: string | null | undefined) {
  return (status ?? 'unknown').replace(/_/g, ' ').toUpperCase();
}

function statusClassName(status: string | null | undefined) {
  const normalizedStatus = (status ?? '').toLowerCase();

  if (normalizedStatus.includes('approve')) {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }

  if (normalizedStatus.includes('reject')) {
    return 'border-rose-200 bg-rose-50 text-rose-700';
  }

  if (normalizedStatus.includes('pending')) {
    return 'border-blue-200 bg-blue-50 text-blue-700';
  }

  if (
    normalizedStatus.includes('test') ||
    normalizedStatus.includes('review') ||
    normalizedStatus.includes('extra')
  ) {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }

  return 'border-slate-200 bg-slate-50 text-slate-700';
}

function priorityLabel(item: ClinicalHypothesis) {
  if (item.severity === 'high') {
    return 'High';
  }

  if (item.severity === 'medium') {
    return 'Medium';
  }

  return 'Low';
}

function priorityClassName(item: ClinicalHypothesis) {
  if (item.severity === 'high') {
    return 'border-rose-200 bg-rose-50 text-rose-700';
  }

  if (item.severity === 'medium') {
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

function uniqueById(items: ClinicalHypothesis[]) {
  const map = new Map<string, ClinicalHypothesis>();

  for (const item of items) {
    map.set(item.id, item);
  }

  return Array.from(map.values());
}

function getEvidenceLabel(item: ClinicalHypothesis) {
  const firstEvidence = item.evidence_json[0];

  if (!firstEvidence) {
    return 'No evidence';
  }

  return (
    firstEvidence.parameter_name ??
    firstEvidence.parameter_code ??
    'Lab signal'
  );
}

function getEvidenceValue(item: ClinicalHypothesis) {
  const firstEvidence = item.evidence_json[0];

  if (!firstEvidence) {
    return '-';
  }

  return `${firstEvidence.value ?? '-'} ${firstEvidence.unit ?? ''}`.trim();
}

function getSignalStatus(item: ClinicalHypothesis) {
  const firstEvidence = item.evidence_json[0];

  return firstEvidence?.result_status ?? item.status;
}

export default function DoctorWorklistPage() {
  const [tasks, setTasks] = useState<ClinicalHypothesis[]>([]);
  const [pendingTasks, setPendingTasks] = useState<ClinicalHypothesis[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const analysisRunId = localStorage.getItem('medicore:lastAnalysisRunId');

  useEffect(() => {
    async function loadWorklist() {
      try {
        setIsLoading(true);
        setError('');

        const pending = await getPendingClinicalHypotheses();
        setPendingTasks(pending);

        if (!analysisRunId) {
          setTasks(pending);
          return;
        }

        const currentRunTasks =
          await getClinicalHypothesesForAnalysisRun(analysisRunId);

        setTasks(uniqueById([...pending, ...currentRunTasks]));
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Unable to load doctor worklist.',
        );
      } finally {
        setIsLoading(false);
      }
    }

    loadWorklist();
  }, [analysisRunId]);

  const selectedTask = useMemo(
    () =>
      pendingTasks[0] ??
      tasks.find((task) => task.needs_doctor_review) ??
      tasks[0],
    [pendingTasks, tasks],
  );

  if (isLoading) {
    return (
      <LoadingState
        title="Loading doctor worklist"
        description="Fetching backend review tasks."
      />
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Unable to load doctor worklist"
        description={error}
      />
    );
  }

  if (tasks.length === 0) {
    return (
      <EmptyState
        title="No worklist tasks"
        description="Create clinical review prompts first, then return here."
        actionLabel="Open clinical review prompts"
        to="/clinical-hypotheses"
      />
    );
  }

  const pendingCount = pendingTasks.length;
  const approvedCount = tasks.filter((task) =>
    task.status.toLowerCase().includes('approve'),
  ).length;
  const rejectedCount = tasks.filter((task) =>
    task.status.toLowerCase().includes('reject'),
  ).length;
  const needsReviewCount = tasks.filter(
    (task) => task.needs_doctor_review,
  ).length;
  const evidenceCount = tasks.reduce(
    (total, task) => total + task.evidence_json.length,
    0,
  );
  const highPriorityCount = tasks.filter(
    (task) => task.severity === 'high',
  ).length;
  const mediumPriorityCount = tasks.filter(
    (task) => task.severity === 'medium',
  ).length;

  const summaryCards = [
    {
      title: 'Total tasks',
      value: tasks.length,
      helper: 'Backend clinical review tasks',
    },
    {
      title: 'Pending review',
      value: pendingCount,
      helper: 'Tasks waiting for doctor action',
    },
    {
      title: 'Approved',
      value: approvedCount,
      helper: 'Reviewed and approved prompts',
    },
    {
      title: 'Rejected',
      value: rejectedCount,
      helper: 'Reviewed and rejected prompts',
    },
    {
      title: 'Evidence signals',
      value: evidenceCount,
      helper: 'Linked lab result signals',
    },
  ];

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-semibold uppercase text-cyan-700">
          Doctor Worklist
        </p>

        <h2 className="mt-2 text-3xl font-semibold text-slate-950">
          Doctor worklist
        </h2>

        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          Backend-connected task queue for physician review prompts, pending
          actions, reviewed items, and linked lab evidence.
        </p>

        <p className="mt-3 inline-flex rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs font-medium text-blue-800">
          Clinical outputs are structured for physician review and are not a
          diagnosis.
        </p>

        {analysisRunId && (
          <div className="mt-4 rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-500">
            Analysis run ID: {analysisRunId}
          </div>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
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

      <div className="grid gap-6 xl:grid-cols-[1.35fr_0.95fr]">
        <SectionCard
          title="Priority task queue"
          description="Backend clinical review prompts shown as doctor worklist tasks."
        >
          <div className="overflow-hidden rounded-lg border border-slate-200">
            <div className="overflow-x-auto">
              <table className="min-w-[980px] divide-y divide-slate-200">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Task
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Signal
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Priority
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Created
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Evidence
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Route
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-slate-200 bg-white">
                  {tasks.map((task) => (
                    <tr key={task.id}>
                      <td className="min-w-80 px-4 py-4 align-top">
                        <p className="font-medium text-slate-950">
                          {task.title}
                        </p>

                        <p className="mt-1 line-clamp-3 text-sm leading-6 text-slate-500">
                          {task.summary}
                        </p>
                      </td>

                      <td className="min-w-40 px-4 py-4 align-top text-slate-600">
                        <p className="font-medium text-slate-800">
                          {getEvidenceLabel(task)}
                        </p>

                        <p className="mt-1 text-sm text-slate-500">
                          {getEvidenceValue(task)}
                        </p>

                        <span
                          className={`mt-2 inline-flex whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                            getSignalStatus(task),
                          )}`}
                        >
                          {statusLabel(getSignalStatus(task))}
                        </span>
                      </td>

                      <td className="px-4 py-4 align-top">
                        <span
                          className={`inline-flex whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs font-semibold ${priorityClassName(
                            task,
                          )}`}
                        >
                          {priorityLabel(task)}
                        </span>
                      </td>

                      <td className="px-4 py-4 align-top">
                        <span
                          className={`inline-flex min-w-28 justify-center whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                            task.status,
                          )}`}
                        >
                          {statusLabel(task.status)}
                        </span>
                      </td>

                      <td className="min-w-40 px-4 py-4 align-top text-slate-600">
                        {formatDate(task.created_at)}
                      </td>

                      <td className="px-4 py-4 align-top text-slate-600">
                        {task.evidence_json.length}
                      </td>

                      <td className="px-4 py-4 align-top">
                        <Link
                          to="/doctor-review"
                          className="inline-flex whitespace-nowrap rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-2 text-sm font-medium text-cyan-800 transition hover:bg-cyan-100"
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
        </SectionCard>

        <SectionCard
          title="Task detail preview"
          description="Selected backend task detail for physician review."
        >
          <article className="rounded-lg border border-slate-200 bg-slate-50 p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Selected review task
                </p>

                <h3 className="mt-2 text-xl font-semibold text-slate-950">
                  {selectedTask.title}
                </h3>
              </div>

              <span
                className={`w-fit whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                  selectedTask.status,
                )}`}
              >
                {statusLabel(selectedTask.status)}
              </span>
            </div>

            <div className="mt-5 grid gap-3">
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Linked signal
                </p>

                <p className="mt-2 font-medium text-slate-950">
                  {getEvidenceLabel(selectedTask)}
                </p>

                <p className="mt-1 text-sm text-slate-600">
                  {getEvidenceValue(selectedTask)}
                </p>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Priority
                </p>

                <span
                  className={`mt-2 inline-flex whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs font-semibold ${priorityClassName(
                    selectedTask,
                  )}`}
                >
                  {priorityLabel(selectedTask)}
                </span>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Description
                </p>

                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {selectedTask.summary}
                </p>
              </div>

              <div className="rounded-lg border border-amber-100 bg-amber-50 p-4">
                <p className="text-xs font-semibold uppercase text-amber-700">
                  Patient visibility impact
                </p>

                <p className="mt-2 text-sm leading-6 text-slate-700">
                  Patient-facing visibility remains blocked until physician
                  approval.
                </p>
              </div>

              <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
                <p className="text-xs font-semibold uppercase text-blue-700">
                  Next review step
                </p>

                <p className="mt-2 text-sm leading-6 text-slate-700">
                  Open Doctor Review to approve, reject, or request extra tests.
                </p>
              </div>

              <Link
                to="/doctor-review"
                className="inline-flex w-fit rounded-lg border border-cyan-200 bg-white px-3 py-2 text-sm font-medium text-cyan-800 transition hover:bg-cyan-50"
              >
                Open doctor review
              </Link>
            </div>
          </article>
        </SectionCard>
      </div>

      <SectionCard
        title="Worklist buckets"
        description="Grouped backend review task buckets."
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <span className="inline-flex whitespace-nowrap rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">
              PENDING
            </span>

            <h3 className="mt-4 font-semibold text-slate-950">
              Pending review
            </h3>

            <p className="mt-3 text-3xl font-semibold text-slate-950">
              {pendingCount}
            </p>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Clinical review prompts waiting for physician action.
            </p>
          </article>

          <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <span className="inline-flex whitespace-nowrap rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
              APPROVED
            </span>

            <h3 className="mt-4 font-semibold text-slate-950">
              Approved prompts
            </h3>

            <p className="mt-3 text-3xl font-semibold text-slate-950">
              {approvedCount}
            </p>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Prompts that passed physician review.
            </p>
          </article>

          <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <span className="inline-flex whitespace-nowrap rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-700">
              REJECTED
            </span>

            <h3 className="mt-4 font-semibold text-slate-950">
              Rejected prompts
            </h3>

            <p className="mt-3 text-3xl font-semibold text-slate-950">
              {rejectedCount}
            </p>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Prompts rejected during doctor review.
            </p>
          </article>

          <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <span className="inline-flex whitespace-nowrap rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700">
              REVIEW
            </span>

            <h3 className="mt-4 font-semibold text-slate-950">
              Needs review flag
            </h3>

            <p className="mt-3 text-3xl font-semibold text-slate-950">
              {needsReviewCount}
            </p>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Items marked as requiring physician review.
            </p>
          </article>

          <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <span className="inline-flex whitespace-nowrap rounded-lg border border-cyan-200 bg-cyan-50 px-2.5 py-1 text-xs font-semibold text-cyan-700">
              EVIDENCE
            </span>

            <h3 className="mt-4 font-semibold text-slate-950">
              Evidence signals
            </h3>

            <p className="mt-3 text-3xl font-semibold text-slate-950">
              {evidenceCount}
            </p>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Lab signals linked to worklist tasks.
            </p>
          </article>
        </div>
      </SectionCard>

      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <SectionCard
          title="SLA and due status"
          description="Operational labels based on backend task status."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
              <p className="text-xs font-semibold uppercase text-blue-700">
                Current queue
              </p>

              <p className="mt-2 text-sm leading-6 text-slate-700">
                {pendingCount} pending task{pendingCount === 1 ? '' : 's'} in
                the doctor review queue.
              </p>
            </div>

            <div className="rounded-lg border border-amber-100 bg-amber-50 p-4">
              <p className="text-xs font-semibold uppercase text-amber-700">
                Action state
              </p>

              <p className="mt-2 text-sm leading-6 text-slate-700">
                Pending prompts remain blocked from patient-facing use until
                physician review is recorded.
              </p>
            </div>

            <div className="rounded-lg border border-rose-100 bg-rose-50 p-4">
              <p className="text-xs font-semibold uppercase text-rose-700">
                High priority
              </p>

              <p className="mt-2 text-sm leading-6 text-slate-700">
                {highPriorityCount} high-priority prompt
                {highPriorityCount === 1 ? '' : 's'} currently shown.
              </p>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-xs font-semibold uppercase text-slate-500">
                Medium priority
              </p>

              <p className="mt-2 text-sm leading-6 text-slate-700">
                {mediumPriorityCount} medium-priority prompt
                {mediumPriorityCount === 1 ? '' : 's'} currently shown.
              </p>
            </div>
          </div>
        </SectionCard>

        <SectionCard
          title="Evidence preview"
          description="Linked lab evidence from current worklist tasks."
        >
          <div className="grid gap-3 md:grid-cols-2">
            {tasks.flatMap((task) =>
              task.evidence_json.map((evidence, index) => (
                <article
                  key={`${task.id}-${index}`}
                  className="rounded-lg border border-slate-200 bg-slate-50 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-slate-950">
                        {evidence.parameter_name ??
                          evidence.parameter_code ??
                          'Lab signal'}
                      </p>

                      <p className="mt-1 text-sm text-slate-600">
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

                  <p className="mt-3 rounded-lg border border-blue-100 bg-white p-3 text-sm leading-6 text-slate-600">
                    {evidence.note ??
                      'Structured evidence signal prepared for physician review.'}
                  </p>
                </article>
              )),
            )}
          </div>
        </SectionCard>
      </div>
    </div>
  );
}