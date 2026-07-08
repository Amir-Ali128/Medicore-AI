import {
  demoPatient,
  mockAnalysisActions,
  mockAnalysisGroups,
  mockAnalysisResultActions,
  mockAnalysisResultReviewNotes,
  mockAnalysisSteps,
  mockAnalysisTrendPreviews,
  mockClinicalEvidenceSignals,
  mockClinicalHypotheses,
  mockClinicalHypothesisNavigationActions,
  mockClinicalReviewActions,
  mockClinicalReviewWorkflowSteps,
  mockDashboardQueue,
  mockDoctorEditedSummaryPreview,
  mockDoctorReviewActions,
  mockDoctorReviewCase,
  mockDoctorReviewEvidence,
  mockDoctorReviewNavigationActions,
  mockDoctorReviewOutcomeExamples,
  mockDoctorReviewPrompt,
  mockDoctorReviewWorkflowSteps,
  mockDoctorWorklistActions,
  mockDoctorWorklistBuckets,
  mockDoctorWorklistNavigationActions,
  mockDoctorWorklistSlaItems,
  mockDoctorWorklistTasks,
  mockExtractedLabValues,
  mockExtractionJob,
  mockExtractionReviewActions,
  mockExtractionReviewValues,
  mockLabResults,
  mockPatientReportSummary,
  mockPatientShortcuts,
  mockPatientTimelineActions,
  mockPatientTimelineEvents,
  mockPatientTimelineStages,
  mockQuickActions,
  mockStats,
  mockTimelineEvents,
} from '../data/mockData';

const delay = (ms = 150) =>
  new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });

export const getDashboardMock = async () => {
  await delay();

  return {
    mockStats,
    mockDashboardQueue,
    mockQuickActions,
    mockLabResults,
    mockTimelineEvents,
  };
};

export const getPatientDetailMock = async () => {
  await delay();

  return {
    demoPatient,
    mockPatientReportSummary,
    mockPatientShortcuts,
    mockLabResults,
    mockClinicalHypotheses,
    mockTimelineEvents,
  };
};

export const getMockAnalysisMock = async () => {
  await delay();

  return {
    mockLabResults,
    mockExtractedLabValues,
    mockAnalysisSteps,
    mockAnalysisActions,
    mockClinicalHypotheses,
  };
};

export const getExtractionReviewMock = async () => {
  await delay();

  return {
    mockExtractionJob,
    mockExtractionReviewValues,
    mockExtractionReviewActions,
  };
};

export const getAnalysisResultsMock = async () => {
  await delay();

  return {
    mockLabResults,
    mockClinicalHypotheses,
    mockAnalysisGroups,
    mockAnalysisResultReviewNotes,
    mockAnalysisTrendPreviews,
    mockAnalysisResultActions,
  };
};

export const getClinicalHypothesesMock = async () => {
  await delay();

  return {
    mockClinicalHypotheses,
    mockClinicalEvidenceSignals,
    mockClinicalReviewActions,
    mockClinicalReviewWorkflowSteps,
    mockClinicalHypothesisNavigationActions,
  };
};

export const getDoctorReviewMock = async () => {
  await delay();

  return {
    mockDoctorReviewCase,
    mockDoctorReviewPrompt,
    mockDoctorReviewEvidence,
    mockDoctorReviewActions,
    mockDoctorEditedSummaryPreview,
    mockDoctorReviewWorkflowSteps,
    mockDoctorReviewOutcomeExamples,
    mockDoctorReviewNavigationActions,
  };
};

export const getPatientTimelineMock = async () => {
  await delay();

  return {
    mockPatientTimelineEvents,
    mockPatientTimelineStages,
    mockPatientTimelineActions,
  };
};

export const getDoctorWorklistMock = async () => {
  await delay();

  return {
    mockDoctorWorklistTasks,
    mockDoctorWorklistBuckets,
    mockDoctorWorklistSlaItems,
    mockDoctorWorklistActions,
    mockDoctorWorklistNavigationActions,
  };
};
