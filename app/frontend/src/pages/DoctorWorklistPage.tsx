import { useEffect, useState } from 'react';
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
    normalizedStatus.includes('review')
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
        description="Create a clinical review prompt first, then return here."
        actionLabel="Open clinical hypotheses"
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

  const selectedTask =
    pendingTasks[0] ??
    tasks.find((task) => task.needs_doctor_review) ??
    tasks[0];

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

      <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
        <SectionCard
          title="Priority task queue"
          description="Backend clinical hypotheses shown as doctor worklist tasks."
        >
          <div className="overflow-hidden rounded-lg border border-slate-200">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Task
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                      Type
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
                      <td className="min-w-72 px-4 py-4">
                        <p className="font-medium text-slate-950">
                          {task.title}
                        </p>

                        <p className="mt-1 text-sm leading-6 text-slate-500">
                          {task.summary}
                        </p>
                      </td>

                      <td className="px-4 py-4 text-slate-600">
                        {task.hypothesis_type ?? 'clinical_review'}
                      </td>

                      <td className="px-4 py-4">
                        <span
                          className={`rounded-lg border px-2.5 py-1 text-xs font-semibold ${priorityClassName(
                            task,
                          )}`}
                        >
                          {priorityLabel(task)}
                        </span>
                      </td>

                      <td className="px-4 py-4">
                        <span
                          className={`rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                            task.status,
                          )}`}
                        >
                          {statusLabel(task.status)}
                        </span>
                      </td>

                      <td className="px-4 py-4 text-slate-600">
                        {formatDate(task.created_at)}
                      </td>

                      <td className="px-4 py-4 text-slate-600">
                        {task.evidence_json.length}
                      </td>

                      <td className="px-4 py-4">
                        <Link
                          to="/doctor-review"
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
                className={`w-fit rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                  selectedTask.status,
                )}`}
              >
                {statusLabel(selectedTask.status)}
              </span>
            </div>

            <div className="mt-5 grid gap-3">
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Priority
                </p>

                <span
                  className={`mt-2 inline-flex rounded-lg border px-2.5 py-1 text-xs font-semibold ${priorityClassName(
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
                Open related route
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
            <span className="rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">
              PENDING
            </span>

            <h3 className="mt-4 font-semibold text-slate-950">
              Pending review
            </h3>

            <p className="mt-3 text-3xl font-semibold text-slate-950">
              {pendingCount}
            </p>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Clinical prompts waiting for physician action.
            </p>
          </article>

          <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <span className="rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
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
            <span className="rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-700">
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
            <span className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700">
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
            <span className="rounded-lg border border-cyan-200 bg-cyan-50 px-2.5 py-1 text-xs font-semibold text-cyan-700">
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
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-start justify-between gap-3">
                <h3 className="font-semibold text-slate-950">
                  Pending queue
                </h3>

                <span className="rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">
                  ACTIVE
                </span>
              </div>

              <p className="mt-3 text-sm leading-6 text-slate-600">
                Pending prompts should be reviewed by a physician before any
                patient-facing visibility.
              </p>
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-start justify-between gap-3">
                <h3 className="font-semibold text-slate-950">
                  Reviewed queue
                </h3>

                <span className="rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                  TRACKED
                </span>
              </div>

              <p className="mt-3 text-sm leading-6 text-slate-600">
                Reviewed prompts remain visible in the current analysis-run
                worklist when available.
              </p>
            </div>
          </div>
        </SectionCard>

        <SectionCard
          title="Safe task actions"
          description="Navigation controls for the backend-connected review flow."
        >
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Link
              to="/doctor-review"
              className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-cyan-200 hover:bg-cyan-50"
            >
              <span className="font-semibold text-slate-950">
                Open doctor review
              </span>

              <span className="mt-2 block text-sm leading-6 text-slate-500">
                Approve, reject, or request extra tests.
              </span>
            </Link>

            <Link
              to="/clinical-hypotheses"
              className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-cyan-200 hover:bg-cyan-50"
            >
              <span className="font-semibold text-slate-950">
                Create review prompt
              </span>

              <span className="mt-2 block text-sm leading-6 text-slate-500">
                Generate a prompt from backend lab results.
              </span>
            </Link>

            <Link
              to="/analysis/results"
              className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-cyan-200 hover:bg-cyan-50"
            >
              <span className="font-semibold text-slate-950">
                View lab results
              </span>

              <span className="mt-2 block text-sm leading-6 text-slate-500">
                Open structured backend analysis results.
              </span>
            </Link>

            <Link
              to="/analysis/mock"
              className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-cyan-200 hover:bg-cyan-50"
            >
              <span className="font-semibold text-slate-950">
                Run analysis
              </span>

              <span className="mt-2 block text-sm leading-6 text-slate-500">
                Start a new backend mock analysis.
              </span>
            </Link>
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="Safety framing"
        description="Worklist items remain physician-review tasks."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Worklist tasks are review prompts, not diagnoses.
            </p>
          </div>

          <div className="rounded-lg border border-cyan-100 bg-cyan-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Tasks do not approve clinical content automatically.
            </p>
          </div>

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Patient-facing content remains blocked until doctor approval.
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