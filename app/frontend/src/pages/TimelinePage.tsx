import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import EmptyState from '../components/ui/EmptyState';
import ErrorState from '../components/ui/ErrorState';
import LoadingState from '../components/ui/LoadingState';
import SectionCard from '../components/ui/SectionCard';
import {
  getClinicalHypothesesForAnalysisRun,
  type ClinicalHypothesis,
} from '../services/clinicalHypothesesClient';
import {
  getAnalysisRunResults,
  type LabAnalysisResult,
} from '../services/labAnalysisClient';

type TimelineEvent = {
  id: string;
  eventType: string;
  title: string;
  description: string;
  status: string;
  timestamp: string | null;
  actor: string;
  source: string;
  relatedRoute: string;
  patientVisibilityImpact: string;
};

type TimelineStage = {
  name: string;
  status: string;
  description: string;
  relatedRoute: string;
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

function eventTypeClassName(eventType: string) {
  const normalizedType = eventType.toLowerCase();

  if (normalizedType.includes('doctor')) {
    return 'text-emerald-700';
  }

  if (normalizedType.includes('clinical')) {
    return 'text-amber-700';
  }

  if (normalizedType.includes('lab')) {
    return 'text-cyan-700';
  }

  return 'text-blue-700';
}

function formatDate(value: string | null) {
  if (!value) {
    return 'Current workflow';
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

function getEventTimeValue(event: TimelineEvent) {
  if (!event.timestamp) {
    return 0;
  }

  const parsed = Date.parse(event.timestamp);

  if (Number.isNaN(parsed)) {
    return 0;
  }

  return parsed;
}

function getAbnormalResults(results: LabAnalysisResult[]) {
  return results.filter(
    (result) =>
      result.result_status === 'low' || result.result_status === 'high',
  );
}

function getPendingHypotheses(hypotheses: ClinicalHypothesis[]) {
  return hypotheses.filter((hypothesis) =>
    hypothesis.status.toLowerCase().includes('pending'),
  );
}

function getReviewedHypotheses(hypotheses: ClinicalHypothesis[]) {
  return hypotheses.filter((hypothesis) => {
    const status = hypothesis.status.toLowerCase();

    return !status.includes('pending');
  });
}

function getDoctorReviewHypotheses(hypotheses: ClinicalHypothesis[]) {
  return hypotheses.filter((hypothesis) => {
    const status = hypothesis.status.toLowerCase();

    return (
      status.includes('approved') ||
      status.includes('rejected') ||
      status.includes('extra') ||
      status.includes('test')
    );
  });
}

function buildResultSummary(results: LabAnalysisResult[]) {
  if (results.length === 0) {
    return 'No structured lab result rows are available for this analysis run.';
  }

  const abnormalResults = getAbnormalResults(results);

  if (abnormalResults.length === 0) {
    return `${results.length} structured lab result row loaded. No abnormal signal is currently marked.`;
  }

  const firstAbnormal = abnormalResults[0];
  const parameterName =
    firstAbnormal.canonical_name ?? firstAbnormal.raw_parameter_name;

  return `${results.length} structured lab result row loaded. ${parameterName} is marked ${statusLabel(
    firstAbnormal.result_status,
  )}.`;
}

function buildDoctorReviewDescription(hypothesis: ClinicalHypothesis) {
  const status = hypothesis.status.toLowerCase();

  if (status.includes('approved')) {
    return 'Physician review approved this clinical review prompt.';
  }

  if (status.includes('rejected')) {
    return 'Physician review rejected this clinical review prompt.';
  }

  if (status.includes('extra') || status.includes('test')) {
    return 'Physician review requested extra testing before patient-facing visibility.';
  }

  return 'Physician review action was recorded for this clinical review prompt.';
}

function buildTimelineEvents(
  analysisRunId: string,
  labReportId: string | null,
  results: LabAnalysisResult[],
  hypotheses: ClinicalHypothesis[],
): TimelineEvent[] {
  const abnormalResults = getAbnormalResults(results);
  const reviewedHypotheses = getReviewedHypotheses(hypotheses);
  const firstKnownTimestamp =
    hypotheses[0]?.created_at ?? reviewedHypotheses[0]?.updated_at ?? null;

  const baseEvents: TimelineEvent[] = [
    {
      id: 'analysis-run-selected',
      eventType: 'Intake',
      title: 'Analysis run selected',
      description:
        'The latest backend analysis run was selected from local workflow state.',
      status: 'completed',
      timestamp: firstKnownTimestamp,
      actor: 'Frontend workflow',
      source: analysisRunId,
      relatedRoute: '/analysis/results',
      patientVisibilityImpact:
        'Patient-facing content stays blocked until physician review is complete.',
    },
    {
      id: 'lab-results-loaded',
      eventType: 'Lab Analysis',
      title: 'Structured lab results loaded',
      description: buildResultSummary(results),
      status: abnormalResults.length > 0 ? 'needs_review' : 'completed',
      timestamp: firstKnownTimestamp,
      actor: 'Backend analysis service',
      source: labReportId ?? 'analysis results endpoint',
      relatedRoute: '/analysis/results',
      patientVisibilityImpact:
        'Lab signals are evidence for physician review, not a diagnosis.',
    },
  ];

  const clinicalPromptEvents: TimelineEvent[] = hypotheses.map((hypothesis) => ({
    id: `clinical-prompt-${hypothesis.id}`,
    eventType: 'Clinical Prompt',
    title: hypothesis.title,
    description: hypothesis.summary,
    status: hypothesis.status,
    timestamp: hypothesis.created_at,
    actor: hypothesis.source,
    source: hypothesis.hypothesis_type ?? 'clinical_review',
    relatedRoute: '/clinical-hypotheses',
    patientVisibilityImpact:
      'Clinical prompt is held for physician review before patient visibility.',
  }));

  const doctorReviewEvents: TimelineEvent[] = reviewedHypotheses.map(
    (hypothesis) => ({
      id: `doctor-review-${hypothesis.id}`,
      eventType: 'Doctor Review',
      title: `Doctor action: ${statusLabel(hypothesis.status)}`,
      description: buildDoctorReviewDescription(hypothesis),
      status: hypothesis.status,
      timestamp: hypothesis.reviewed_at ?? hypothesis.updated_at,
      actor: hypothesis.reviewed_by_user_id
        ? 'Doctor reviewer'
        : 'Doctor review workflow',
      source: hypothesis.source,
      relatedRoute: '/doctor-worklist',
      patientVisibilityImpact:
        hypothesis.status.toLowerCase().includes('approved')
          ? 'Approved prompt can move toward patient-facing visibility after final product rules.'
          : 'Patient-facing content remains blocked.',
    }),
  );

  return [...baseEvents, ...clinicalPromptEvents, ...doctorReviewEvents].sort(
    (first, second) => getEventTimeValue(first) - getEventTimeValue(second),
  );
}

function buildTimelineStages(
  results: LabAnalysisResult[],
  hypotheses: ClinicalHypothesis[],
): TimelineStage[] {
  const pendingHypotheses = getPendingHypotheses(hypotheses);
  const reviewedHypotheses = getReviewedHypotheses(hypotheses);
  const approvedHypotheses = hypotheses.filter((hypothesis) =>
    hypothesis.status.toLowerCase().includes('approved'),
  );

  return [
    {
      name: 'Lab analysis',
      status: results.length > 0 ? 'completed' : 'pending',
      description: `${results.length} backend lab result row loaded for the latest analysis run.`,
      relatedRoute: '/analysis/results',
    },
    {
      name: 'Clinical prompt generation',
      status: hypotheses.length > 0 ? 'created' : 'pending',
      description: `${hypotheses.length} clinical review prompt available for this analysis run.`,
      relatedRoute: '/clinical-hypotheses',
    },
    {
      name: 'Doctor review',
      status:
        pendingHypotheses.length > 0
          ? 'pending_review'
          : reviewedHypotheses.length > 0
            ? 'completed'
            : 'pending',
      description:
        pendingHypotheses.length > 0
          ? `${pendingHypotheses.length} prompt waiting for physician action.`
          : `${reviewedHypotheses.length} prompt has a recorded doctor action.`,
      relatedRoute: '/doctor-review',
    },
    {
      name: 'Patient visibility gate',
      status: approvedHypotheses.length > 0 ? 'reviewed' : 'blocked',
      description:
        approvedHypotheses.length > 0
          ? 'Approved prompt can move toward patient-facing product rules.'
          : 'Patient-facing content remains blocked.',
      relatedRoute: '/patients/demo',
    },
  ];
}

export default function TimelinePage() {
  const [results, setResults] = useState<LabAnalysisResult[]>([]);
  const [hypotheses, setHypotheses] = useState<ClinicalHypothesis[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const analysisRunId = localStorage.getItem('medicore:lastAnalysisRunId');
  const labReportId = localStorage.getItem('medicore:lastLabReportId');

  useEffect(() => {
    async function loadTimeline() {
      if (!analysisRunId) {
        setIsLoading(false);
        return;
      }

      try {
        setIsLoading(true);
        setError('');

        const [analysisResults, clinicalHypotheses] = await Promise.all([
          getAnalysisRunResults(analysisRunId),
          getClinicalHypothesesForAnalysisRun(analysisRunId),
        ]);

        setResults(analysisResults);
        setHypotheses(clinicalHypotheses);
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Unable to load patient timeline.',
        );
      } finally {
        setIsLoading(false);
      }
    }

    loadTimeline();
  }, [analysisRunId]);

  const timelineEvents = useMemo(() => {
    if (!analysisRunId) {
      return [];
    }

    return buildTimelineEvents(analysisRunId, labReportId, results, hypotheses);
  }, [analysisRunId, labReportId, results, hypotheses]);

  const timelineStages = useMemo(
    () => buildTimelineStages(results, hypotheses),
    [results, hypotheses],
  );

  const pendingCount = getPendingHypotheses(hypotheses).length;
  const completedCount = timelineEvents.filter((event) => {
    const status = event.status.toLowerCase();

    return (
      status.includes('completed') ||
      status.includes('approved') ||
      status.includes('rejected')
    );
  }).length;
  const doctorReviewCount = getDoctorReviewHypotheses(hypotheses).length;
  const latestEvent = timelineEvents[timelineEvents.length - 1] ?? null;

  const summaryCards = [
    {
      title: 'Total events',
      value: timelineEvents.length,
      helper: 'Backend workflow timeline events',
    },
    {
      title: 'Completed events',
      value: completedCount,
      helper: 'Events with completed or reviewed state',
    },
    {
      title: 'Pending reviews',
      value: pendingCount,
      helper: 'Clinical prompts waiting on doctor action',
    },
    {
      title: 'Doctor review events',
      value: doctorReviewCount,
      helper: 'Timeline events tied to physician review',
    },
  ];

  if (isLoading) {
    return (
      <LoadingState
        title="Loading patient timeline"
        description="Fetching backend workflow timeline data."
      />
    );
  }

  if (!analysisRunId) {
    return (
      <EmptyState
        title="No timeline data yet"
        description="Run a backend mock analysis first, then create a clinical review prompt."
        actionLabel="Run mock analysis"
        to="/analysis/mock"
      />
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Unable to load patient timeline"
        description={error}
      />
    );
  }

  if (timelineEvents.length === 0) {
    return (
      <EmptyState
        title="No timeline events"
        description="No backend workflow timeline events are available."
        actionLabel="Open demo patient"
        to="/patients/demo"
      />
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-semibold uppercase text-cyan-700">
          Timeline
        </p>

        <h2 className="mt-2 text-3xl font-semibold text-slate-950">
          Patient timeline
        </h2>

        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          Backend-connected timeline for lab-report review activity, from
          analysis through clinical prompts, doctor review, and patient
          visibility controls.
        </p>

        <p className="mt-3 inline-flex rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs font-medium text-blue-800">
          Clinical outputs are structured for physician review and are not a
          diagnosis.
        </p>

        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-500">
            <span className="font-semibold uppercase text-slate-600">
              Analysis run:
            </span>{' '}
            {analysisRunId}
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-500">
            <span className="font-semibold uppercase text-slate-600">
              Lab report:
            </span>{' '}
            {labReportId ?? 'Not stored locally'}
          </div>
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

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <SectionCard
          title="Patient timeline feed"
          description="Backend workflow events for the latest lab-report review workflow."
        >
          <div className="relative space-y-5 before:absolute before:bottom-6 before:left-4 before:top-6 before:w-px before:bg-slate-200">
            {timelineEvents.map((event) => (
              <article key={event.id} className="relative flex gap-4">
                <div className="mt-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-blue-100 bg-blue-50">
                  <span className="h-2.5 w-2.5 rounded-full bg-blue-600" />
                </div>

                <div className="flex-1 rounded-lg border border-slate-200 bg-white p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p
                        className={`text-xs font-semibold uppercase ${eventTypeClassName(
                          event.eventType,
                        )}`}
                      >
                        {event.eventType}
                      </p>

                      <h3 className="mt-1 font-semibold text-slate-950">
                        {event.title}
                      </h3>

                      <p className="mt-2 text-sm leading-6 text-slate-600">
                        {event.description}
                      </p>
                    </div>

                    <span
                      className={`w-fit rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                        event.status,
                      )}`}
                    >
                      {statusLabel(event.status)}
                    </span>
                  </div>

                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <p className="text-xs font-semibold uppercase text-slate-500">
                        Timestamp
                      </p>

                      <p className="mt-2 text-sm font-medium text-slate-950">
                        {formatDate(event.timestamp)}
                      </p>
                    </div>

                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <p className="text-xs font-semibold uppercase text-slate-500">
                        Actor
                      </p>

                      <p className="mt-2 text-sm font-medium text-slate-950">
                        {event.actor}
                      </p>
                    </div>

                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <p className="text-xs font-semibold uppercase text-slate-500">
                        Source
                      </p>

                      <p className="mt-2 break-words text-sm font-medium text-slate-950">
                        {event.source}
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-sm leading-6 text-slate-600">
                      {event.patientVisibilityImpact}
                    </p>

                    <Link
                      to={event.relatedRoute}
                      className="w-fit rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-2 text-sm font-medium text-cyan-800 transition hover:bg-cyan-100"
                    >
                      Open related view
                    </Link>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Event detail"
          description="Latest backend workflow event detail."
        >
          {latestEvent ? (
            <article className="rounded-lg border border-slate-200 bg-slate-50 p-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase text-slate-500">
                    Latest timeline event
                  </p>

                  <h3 className="mt-2 text-xl font-semibold text-slate-950">
                    {latestEvent.title}
                  </h3>
                </div>

                <span
                  className={`w-fit rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                    latestEvent.status,
                  )}`}
                >
                  {statusLabel(latestEvent.status)}
                </span>
              </div>

              <p className="mt-4 text-sm leading-6 text-slate-600">
                {latestEvent.description}
              </p>

              <div className="mt-5 grid gap-3">
                <div className="rounded-lg border border-slate-200 bg-white p-4">
                  <p className="text-xs font-semibold uppercase text-slate-500">
                    Actor
                  </p>

                  <p className="mt-2 font-medium text-slate-950">
                    {latestEvent.actor}
                  </p>
                </div>

                <div className="rounded-lg border border-slate-200 bg-white p-4">
                  <p className="text-xs font-semibold uppercase text-slate-500">
                    Patient visibility impact
                  </p>

                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    {latestEvent.patientVisibilityImpact}
                  </p>
                </div>

                <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
                  <p className="text-xs font-semibold uppercase text-blue-700">
                    Next recommended review step
                  </p>

                  <p className="mt-2 text-sm leading-6 text-slate-700">
                    Open doctor review and complete physician review before any
                    patient-facing content is approved.
                  </p>
                </div>
              </div>
            </article>
          ) : (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              No latest event is available.
            </div>
          )}
        </SectionCard>
      </div>

      <SectionCard
        title="Workflow stage overview"
        description="Stage-level view of the backend lab-report review workflow."
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {timelineStages.map((stage) => (
            <article
              key={stage.name}
              className="rounded-lg border border-slate-200 bg-slate-50 p-4"
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <h3 className="font-semibold text-slate-950">{stage.name}</h3>

                <span
                  className={`w-fit rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                    stage.status,
                  )}`}
                >
                  {statusLabel(stage.status)}
                </span>
              </div>

              <p className="mt-3 text-sm leading-6 text-slate-600">
                {stage.description}
              </p>

              <Link
                to={stage.relatedRoute}
                className="mt-4 inline-flex rounded-lg border border-cyan-200 bg-white px-3 py-2 text-sm font-medium text-cyan-800 transition hover:bg-cyan-50"
              >
                Open stage
              </Link>
            </article>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Doctor review checkpoint"
        description="Patient visibility stays blocked until physician review is complete."
      >
        <div className="grid gap-4 md:grid-cols-4">
          <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Doctor review is required before patient-facing content.
            </p>
          </div>

          <div className="rounded-lg border border-cyan-100 bg-cyan-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Review prompts are not diagnoses.
            </p>
          </div>

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Timeline data is generated from backend workflow state.
            </p>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-sm leading-6 text-slate-700">
              Final decisions belong to a physician.
            </p>
          </div>
        </div>
      </SectionCard>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <SectionCard
          title="Safe navigation"
          description="Links to related backend workflow views."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Link
              to="/patients/demo"
              className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-cyan-200 hover:bg-cyan-50"
            >
              <span className="font-semibold text-slate-950">
                Open patient detail
              </span>

              <span className="mt-2 block text-sm leading-6 text-slate-500">
                View latest backend patient workflow state.
              </span>
            </Link>

            <Link
              to="/doctor-worklist"
              className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-cyan-200 hover:bg-cyan-50"
            >
              <span className="font-semibold text-slate-950">
                Open doctor worklist
              </span>

              <span className="mt-2 block text-sm leading-6 text-slate-500">
                Review all backend clinical tasks.
              </span>
            </Link>

            <Link
              to="/analysis/results"
              className="block rounded-lg border border-slate-200 bg-white p-4 transition hover:border-cyan-200 hover:bg-cyan-50"
            >
              <span className="font-semibold text-slate-950">
                Open analysis results
              </span>

              <span className="mt-2 block text-sm leading-6 text-slate-500">
                Inspect latest structured lab results.
              </span>
            </Link>

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
          </div>
        </SectionCard>

        <SectionCard
          title="Safety framing"
          description="Timeline events are backend workflow records."
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
              <p className="text-sm leading-6 text-slate-700">
                Timeline events are workflow records, not medical conclusions.
              </p>
            </div>

            <div className="rounded-lg border border-cyan-100 bg-cyan-50 p-4">
              <p className="text-sm leading-6 text-slate-700">
                AI/system outputs do not approve themselves.
              </p>
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-sm leading-6 text-slate-700">
                Patient-facing content stays blocked until doctor approval.
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