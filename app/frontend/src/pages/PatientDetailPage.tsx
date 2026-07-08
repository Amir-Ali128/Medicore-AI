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
  phase: string;
  title: string;
  description: string;
  status: string;
  timestamp: string | null;
  actor: string;
  source: string;
  route: string;
};


const DEMO_PATIENT = {
  name: 'Demo Patient',
  age: '22',
  sex: 'Male',
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


function phaseClassName(phase: string) {
  const normalizedPhase = phase.toLowerCase();


  if (normalizedPhase.includes('doctor')) {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }


  if (normalizedPhase.includes('clinical')) {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }


  if (normalizedPhase.includes('lab')) {
    return 'border-cyan-200 bg-cyan-50 text-cyan-700';
  }


  return 'border-blue-200 bg-blue-50 text-blue-700';
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


function formatConfidence(confidence: number | null) {
  if (confidence === null) {
    return '-';
  }


  return `${Math.round(confidence * 100)}%`;
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


function getApprovedHypotheses(hypotheses: ClinicalHypothesis[]) {
  return hypotheses.filter((hypothesis) =>
    hypothesis.status.toLowerCase().includes('approved'),
  );
}


function getRejectedHypotheses(hypotheses: ClinicalHypothesis[]) {
  return hypotheses.filter((hypothesis) =>
    hypothesis.status.toLowerCase().includes('rejected'),
  );
}


function getExtraTestHypotheses(hypotheses: ClinicalHypothesis[]) {
  return hypotheses.filter((hypothesis) => {
    const status = hypothesis.status.toLowerCase();


    return status.includes('extra') || status.includes('test');
  });
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


function buildResultSummary(results: LabAnalysisResult[]) {
  if (results.length === 0) {
    return 'No structured lab result rows are available yet.';
  }


  const abnormalResults = getAbnormalResults(results);


  if (abnormalResults.length === 0) {
    return `${results.length} structured lab result row loaded. No abnormal result status is currently marked.`;
  }


  const firstAbnormal = abnormalResults[0];
  const parameterName =
    firstAbnormal.canonical_name ?? firstAbnormal.raw_parameter_name;


  return `${results.length} structured lab result row loaded. ${parameterName} is marked ${statusLabel(
    firstAbnormal.result_status,
  )}.`;
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
      phase: 'Intake',
      title: 'Analysis run selected',
      description:
        'The latest backend analysis run was selected from local workflow state.',
      status: 'completed',
      timestamp: firstKnownTimestamp,
      actor: 'Frontend workflow',
      source: analysisRunId,
      route: '/analysis/results',
    },
    {
      id: 'lab-results-loaded',
      phase: 'Lab analysis',
      title: 'Structured lab results loaded',
      description: buildResultSummary(results),
      status: abnormalResults.length > 0 ? 'needs_review' : 'completed',
      timestamp: firstKnownTimestamp,
      actor: 'Backend analysis service',
      source: labReportId ?? 'analysis results endpoint',
      route: '/analysis/results',
    },
  ];


  const clinicalPromptEvents: TimelineEvent[] = hypotheses.map((hypothesis) => ({
    id: `clinical-prompt-${hypothesis.id}`,
    phase: 'Clinical review prompt',
    title: hypothesis.title,
    description: hypothesis.summary,
    status: hypothesis.status,
    timestamp: hypothesis.created_at,
    actor: hypothesis.source,
    source: hypothesis.hypothesis_type ?? 'clinical_review',
    route: '/clinical-hypotheses',
  }));


  const doctorReviewEvents: TimelineEvent[] = reviewedHypotheses.map(
    (hypothesis) => ({
      id: `doctor-review-${hypothesis.id}`,
      phase: 'Doctor review',
      title: `Doctor action: ${statusLabel(hypothesis.status)}`,
      description: buildDoctorReviewDescription(hypothesis),
      status: hypothesis.status,
      timestamp: hypothesis.reviewed_at ?? hypothesis.updated_at,
      actor: hypothesis.reviewed_by_user_id
        ? 'Doctor reviewer'
        : 'Doctor review workflow',
      source: hypothesis.source,
      route: '/doctor-worklist',
    }),
  );


  return [...baseEvents, ...clinicalPromptEvents, ...doctorReviewEvents].sort(
    (first, second) => getEventTimeValue(first) - getEventTimeValue(second),
  );
}


export default function PatientDetailPage() {
  const [results, setResults] = useState<LabAnalysisResult[]>([]);
  const [hypotheses, setHypotheses] = useState<ClinicalHypothesis[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');


  const analysisRunId = localStorage.getItem('medicore:lastAnalysisRunId');
  const labReportId = localStorage.getItem('medicore:lastLabReportId');


  useEffect(() => {
    async function loadPatientDetail() {
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
            : 'Unable to load patient detail.',
        );
      } finally {
        setIsLoading(false);
      }
    }


    loadPatientDetail();
  }, [analysisRunId]);


  const timelineEvents = useMemo(() => {
    if (!analysisRunId) {
      return [];
    }


    return buildTimelineEvents(analysisRunId, labReportId, results, hypotheses);
  }, [analysisRunId, labReportId, results, hypotheses]);


  if (isLoading) {
    return (
      <LoadingState
        title="Loading patient detail"
        description="Fetching backend lab results, clinical review prompts, and doctor review status."
      />
    );
  }


  if (!analysisRunId) {
    return (
      <EmptyState
        title="No patient workflow yet"
        description="Upload or run a lab analysis first, then create clinical review prompts."
        actionLabel="Open lab analysis"
        to="/analysis/mock"
      />
    );
  }


  if (error) {
    return (
      <ErrorState
        title="Unable to load patient detail"
        description={error}
      />
    );
  }


  const abnormalLabSignals = getAbnormalResults(results);
  const pendingHypotheses = getPendingHypotheses(hypotheses);
  const reviewedHypotheses = getReviewedHypotheses(hypotheses);
  const approvedHypotheses = getApprovedHypotheses(hypotheses);
  const rejectedHypotheses = getRejectedHypotheses(hypotheses);
  const extraTestHypotheses = getExtraTestHypotheses(hypotheses);


  const latestHypothesis =
    hypotheses[0] ??
    reviewedHypotheses[0] ??
    pendingHypotheses[0] ??
    null;


  const overviewCards = [
    {
      label: 'Latest report status',
      value:
        pendingHypotheses.length > 0
          ? 'Doctor review pending'
          : reviewedHypotheses.length > 0
            ? 'Doctor action recorded'
            : 'Analysis ready',
      helper: 'Backend workflow status for latest analysis run.',
    },
    {
      label: 'Pending doctor reviews',
      value: pendingHypotheses.length.toString(),
      helper: 'Clinical review prompts awaiting doctor action.',
    },
    {
      label: 'Abnormal lab signals',
      value: abnormalLabSignals.length.toString(),
      helper: 'LOW or HIGH lab result statuses.',
    },
    {
      label: 'Timeline events',
      value: timelineEvents.length.toString(),
      helper: 'Backend workflow events in this patient view.',
    },
  ];


  const reportStatusItems = [
    {
      label: 'Analysis status',
      status: results.length > 0 ? 'completed' : 'pending',
      detail: `${results.length} structured lab result row loaded.`,
    },
    {
      label: 'Clinical review prompt status',
      status: hypotheses.length > 0 ? 'created' : 'pending',
      detail: `${hypotheses.length} clinical review prompt available.`,
    },
    {
      label: 'Doctor review status',
      status:
        pendingHypotheses.length > 0
          ? 'pending_review'
          : reviewedHypotheses.length > 0
            ? 'completed'
            : 'pending',
      detail:
        pendingHypotheses.length > 0
          ? 'Pending doctor review'
          : reviewedHypotheses.length > 0
            ? 'Doctor review action recorded'
            : 'No doctor review action yet',
    },
    {
      label: 'Patient visibility',
      status: approvedHypotheses.length > 0 ? 'reviewed' : 'blocked',
      detail:
        approvedHypotheses.length > 0
          ? 'Approved prompts may move toward patient-facing rules.'
          : 'Patient-facing content remains blocked.',
    },
  ];


  return (
    <div className="space-y-8">
      <section className="rounded-lg border border-blue-100 bg-white p-6 shadow-sm lg:p-8">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase text-cyan-700">
              Backend-connected demo patient
            </p>


            <h2 className="mt-3 text-3xl font-semibold text-slate-950 lg:text-4xl">
              Patient profile
            </h2>


            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Name
                </p>


                <p className="mt-1 text-lg font-semibold text-slate-950">
                  {DEMO_PATIENT.name}
                </p>
              </div>


              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Age
                </p>


                <p className="mt-1 text-lg font-semibold text-slate-950">
                  {DEMO_PATIENT.age}
                </p>
              </div>


              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Sex
                </p>


                <p className="mt-1 text-lg font-semibold text-slate-950">
                  {DEMO_PATIENT.sex}
                </p>
              </div>
            </div>
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
            {analysisRunId}
          </div>


          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs text-slate-500">
            <span className="font-semibold uppercase text-slate-600">
              Lab report:
            </span>{' '}
            {labReportId ?? 'Not stored locally'}
          </div>
        </div>
      </section>


      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {overviewCards.map((card) => (
          <article
            key={card.label}
            className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
          >
            <p className="text-sm font-medium text-slate-500">{card.label}</p>


            <p className="mt-3 text-2xl font-semibold text-slate-950">
              {card.value}
            </p>


            <p className="mt-3 text-sm leading-6 text-slate-500">
              {card.helper}
            </p>
          </article>
        ))}
      </div>


      <div className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
        <SectionCard
          title="Latest report summary"
          description="Backend analysis and review status for the latest workflow."
        >
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-sm text-slate-500">Report source</p>


                <p className="mt-1 text-lg font-semibold text-slate-950">
                  {labReportId ? 'Backend lab report' : 'Latest local workflow'}
                </p>
              </div>


              <div className="text-left sm:text-right">
                <p className="text-sm text-slate-500">Latest event</p>


                <p className="mt-1 font-medium text-slate-950">
                  {formatDate(timelineEvents[timelineEvents.length - 1]?.timestamp ?? null)}
                </p>
              </div>
            </div>
          </div>


          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {reportStatusItems.map((item) => (
              <div
                key={item.label}
                className="rounded-lg border border-slate-200 bg-white p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-slate-950">{item.label}</p>


                    <p className="mt-1 text-sm leading-6 text-slate-500">
                      {item.detail}
                    </p>
                  </div>


                  <span
                    className={`w-fit rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                      item.status,
                    )}`}
                  >
                    {statusLabel(item.status)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>


        <SectionCard
          title="Patient workflow shortcuts"
          description="Backend-connected navigation for this demo patient workspace."
        >
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
            <Link
              to="/analysis/results"
              className="rounded-lg border border-slate-200 bg-slate-50 p-4 transition hover:border-blue-200 hover:bg-blue-50"
            >
              <p className="font-semibold text-slate-950">
                View analysis results
              </p>


              <p className="mt-2 text-sm leading-6 text-slate-600">
                Open structured backend lab result rows.
              </p>
            </Link>


            <Link
              to="/clinical-hypotheses"
              className="rounded-lg border border-slate-200 bg-slate-50 p-4 transition hover:border-blue-200 hover:bg-blue-50"
            >
              <p className="font-semibold text-slate-950">
                Clinical review prompts
              </p>


              <p className="mt-2 text-sm leading-6 text-slate-600">
                Create or view generated clinical review prompts.
              </p>
            </Link>


            <Link
              to="/doctor-review"
              className="rounded-lg border border-slate-200 bg-slate-50 p-4 transition hover:border-blue-200 hover:bg-blue-50"
            >
              <p className="font-semibold text-slate-950">Doctor review</p>


              <p className="mt-2 text-sm leading-6 text-slate-600">
                Approve, reject, or request extra tests.
              </p>
            </Link>


            <Link
              to="/doctor-worklist"
              className="rounded-lg border border-slate-200 bg-slate-50 p-4 transition hover:border-blue-200 hover:bg-blue-50"
            >
              <p className="font-semibold text-slate-950">Doctor worklist</p>


              <p className="mt-2 text-sm leading-6 text-slate-600">
                View all backend review tasks.
              </p>
            </Link>
          </div>
        </SectionCard>
      </div>


      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <SectionCard
          title="Lab signal summary"
          description="Structured lab signal values from backend analysis results."
        >
          {results.length === 0 ? (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              No backend lab result rows were returned for this analysis run.
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {results.map((result) => (
                <div
                  key={result.lab_result_id}
                  className={`rounded-lg border p-4 ${
                    result.result_status === 'low' ||
                    result.result_status === 'high'
                      ? 'border-blue-200 bg-blue-50'
                      : 'border-slate-200 bg-slate-50'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="font-medium text-slate-950">
                      {result.canonical_name ?? result.raw_parameter_name}
                    </p>


                    <span
                      className={`w-fit rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                        result.result_status,
                      )}`}
                    >
                      {statusLabel(result.result_status)}
                    </span>
                  </div>


                  <p className="mt-3 text-sm font-medium text-slate-700">
                    {result.normalized_value} {result.unit}
                  </p>


                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    Reference: {result.reference_min ?? '-'} -{' '}
                    {result.reference_max ?? '-'} {result.unit}
                  </p>


                  <p className="mt-3 rounded-lg border border-blue-100 bg-white p-3 text-xs leading-5 text-slate-600">
                    {result.reason}
                  </p>
                </div>
              ))}
            </div>
          )}
        </SectionCard>


        <SectionCard
          title="Recent timeline preview"
          description="Latest backend workflow events for this demo patient."
        >
          <div className="space-y-3">
            {timelineEvents.slice(-5).map((event) => (
              <div
                key={event.id}
                className="flex items-center justify-between gap-4 rounded-lg border border-slate-200 bg-slate-50 p-4"
              >
                <div>
                  <p className="font-medium text-slate-950">{event.title}</p>


                  <p className="mt-1 text-sm text-slate-500">
                    {formatDate(event.timestamp)}
                  </p>


                  <p className="mt-1 text-xs text-slate-500">
                    {event.phase} · {event.actor}
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
            ))}
          </div>
        </SectionCard>
      </div>


      <div className="grid gap-6 xl:grid-cols-[1fr_0.85fr]">
        <SectionCard
          title="Clinical review prompts"
          description="Backend clinical review prompts linked to this analysis run."
        >
          {hypotheses.length === 0 ? (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              No clinical review prompts exist for this analysis run yet.
            </div>
          ) : (
            <div className="grid gap-4">
              {hypotheses.map((hypothesis) => (
                <article
                  key={hypothesis.id}
                  className="rounded-lg border border-slate-200 bg-slate-50 p-4"
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


                    <span
                      className={`w-fit rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusClassName(
                        hypothesis.status,
                      )}`}
                    >
                      {statusLabel(hypothesis.status)}
                    </span>
                  </div>


                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    <div className="rounded-lg border border-slate-200 bg-white p-3">
                      <p className="text-xs font-semibold uppercase text-slate-500">
                        Severity
                      </p>


                      <span
                        className={`mt-2 inline-flex rounded-lg border px-2.5 py-1 text-xs font-semibold ${severityClassName(
                          hypothesis.severity,
                        )}`}
                      >
                        {(hypothesis.severity ?? 'low').toUpperCase()}
                      </span>
                    </div>


                    <div className="rounded-lg border border-slate-200 bg-white p-3">
                      <p className="text-xs font-semibold uppercase text-slate-500">
                        Confidence
                      </p>


                      <p className="mt-2 text-sm font-medium text-slate-950">
                        {formatConfidence(hypothesis.confidence)}
                      </p>
                    </div>


                    <div className="rounded-lg border border-slate-200 bg-white p-3">
                      <p className="text-xs font-semibold uppercase text-slate-500">
                        Evidence
                      </p>


                      <p className="mt-2 text-sm font-medium text-slate-950">
                        {hypothesis.evidence_json.length}
                      </p>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </SectionCard>


        <SectionCard
          title="Review status breakdown"
          description="Doctor review actions recorded for this patient workflow."
        >
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
              <p className="text-xs font-semibold uppercase text-blue-700">
                Pending
              </p>


              <p className="mt-3 text-3xl font-semibold text-slate-950">
                {pendingHypotheses.length}
              </p>
            </div>


            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
              <p className="text-xs font-semibold uppercase text-emerald-700">
                Approved
              </p>


              <p className="mt-3 text-3xl font-semibold text-slate-950">
                {approvedHypotheses.length}
              </p>
            </div>


            <div className="rounded-lg border border-rose-200 bg-rose-50 p-4">
              <p className="text-xs font-semibold uppercase text-rose-700">
                Rejected
              </p>


              <p className="mt-3 text-3xl font-semibold text-slate-950">
                {rejectedHypotheses.length}
              </p>
            </div>


            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
              <p className="text-xs font-semibold uppercase text-amber-700">
                Extra test requested
              </p>


              <p className="mt-3 text-3xl font-semibold text-slate-950">
                {extraTestHypotheses.length}
              </p>
            </div>
          </div>


          {latestHypothesis && (
            <div className="mt-4 rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-xs font-semibold uppercase text-slate-500">
                Latest prompt
              </p>


              <p className="mt-2 text-sm font-medium text-slate-950">
                {latestHypothesis.title}
              </p>


              <p className="mt-2 text-xs leading-5 text-slate-500">
                {statusLabel(latestHypothesis.status)}
              </p>
            </div>
          )}
        </SectionCard>
      </div>


      <SectionCard
        title="Safety framing"
        description="Patient detail shows workflow state, not medical advice."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Patient detail events are workflow records, not diagnoses.
            </p>
          </div>


          <div className="rounded-lg border border-cyan-100 bg-cyan-50 p-4">
            <p className="text-sm leading-6 text-slate-700">
              Clinical review prompts remain under physician review controls.
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