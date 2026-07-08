export type LabStatus = 'NORMAL' | 'LOW' | 'HIGH';

export type DemoPatient = {
  name: string;
  age: number;
  sex: 'Male';
  patientId: string;
};

export type LabResult = {
  name: string;
  value: string;
  referenceRange: string;
  status: LabStatus;
};

export type TimelineEvent = {
  title: string;
  status: 'CREATED' | 'COMPLETED' | 'PENDING';
  time: string;
};

export type MockStat = {
  title: string;
  value: string;
  helper: string;
  accent: 'blue' | 'cyan' | 'slate';
};

export type ClinicalHypothesis = {
  title: string;
  observation: string;
  reviewFocus: string;
  status: 'PENDING' | 'CREATED' | 'APPROVED' | 'EDITED' | 'REJECTED';
  priority: 'Low' | 'Medium' | 'High';
  confidenceLabel: string;
  generatedAt: string;
  source: string;
  evidenceMarkers: string[];
};

export type DashboardQueueItem = {
  patientName: string;
  type: string;
  priority: 'Low' | 'Medium' | 'High';
  status: 'PENDING' | 'CREATED' | 'COMPLETED';
  description: string;
};

export type QuickAction = {
  label: string;
  description: string;
  to: string;
};

export type PatientReportSummary = {
  reportName: string;
  uploadedAt: string;
  extractionStatus: 'PENDING' | 'CREATED' | 'COMPLETED';
  analysisStatus: 'PENDING' | 'CREATED' | 'COMPLETED';
  hypothesisStatus: 'PENDING' | 'CREATED' | 'COMPLETED';
  doctorReviewStatus: 'PENDING' | 'CREATED' | 'COMPLETED';
};

export type PatientShortcut = {
  label: string;
  description: string;
  to: string;
};

export type MockExtractedLabValue = {
  markerName: string;
  extractedValue: string;
  referenceRange: string;
  confidence: string;
  reviewStatus: 'PENDING' | 'CREATED' | 'COMPLETED';
};

export type MockAnalysisStep = {
  title: string;
  description: string;
  status: 'PENDING' | 'CREATED' | 'COMPLETED';
};

export type MockAnalysisAction = {
  label: string;
  description: string;
  to?: string;
  disabled?: boolean;
};

export type ExtractionReviewStatus =
  | 'PENDING'
  | 'APPROVED'
  | 'EDITED'
  | 'REJECTED';

export type MockExtractionJob = {
  fileName: string;
  patientName: string;
  source: string;
  extractionStatus: 'PENDING' | 'CREATED' | 'COMPLETED';
  reviewStatus: ExtractionReviewStatus;
  createdAt: string;
  reviewedValuesCount: number;
};

export type MockExtractionReviewValue = {
  markerName: string;
  extractedValue: string;
  referenceRange: string;
  confidence: string;
  reviewStatus: ExtractionReviewStatus;
  reviewerNote: string;
  actionState: string;
};

export type MockExtractionReviewAction = {
  label: string;
  description: string;
  to?: string;
  disabled?: boolean;
};

export type AnalysisGroupOverview = {
  name: string;
  description: string;
  markers: string[];
  flaggedCount: number;
  reviewStatus: 'PENDING' | 'CREATED' | 'COMPLETED';
};

export type AnalysisResultReviewNote = {
  markerName: string;
  note: string;
};

export type AnalysisTrendPreview = {
  markerName: string;
  direction: 'Up' | 'Down' | 'Stable';
  previousValue: string;
  currentValue: string;
  note: string;
};

export type AnalysisResultAction = {
  label: string;
  description: string;
  to: string;
};

export type ClinicalEvidenceSignal = {
  markerName: string;
  value: string;
  status: 'NORMAL' | 'LOW' | 'HIGH';
  relatedHypothesisTitle: string;
  evidenceNote: string;
};

export type ClinicalReviewAction = {
  label: string;
  description: string;
  disabled?: boolean;
};

export type ClinicalReviewWorkflowStep = {
  title: string;
  description: string;
  status: 'PENDING' | 'CREATED' | 'COMPLETED';
};

export type ClinicalHypothesisNavigationAction = {
  label: string;
  description: string;
  to: string;
};

export type DoctorReviewStatus =
  | 'PENDING'
  | 'APPROVED'
  | 'EDITED'
  | 'REJECTED'
  | 'EXTRA_TEST_REQUESTED'
  | 'SPECIALIST_REFERRED';

export type DoctorReviewCase = {
  patientName: string;
  reportName: string;
  reviewStatus: DoctorReviewStatus;
  assignedRole: string;
  generatedAt: string;
  pendingActionCount: number;
  patientVisibilityStatus: string;
};

export type DoctorReviewPrompt = {
  title: string;
  observation: string;
  reviewFocus: string;
  priority: 'Low' | 'Medium' | 'High';
  confidenceLabel: string;
  source: string;
  generatedAt: string;
  evidenceMarkers: string[];
};

export type DoctorReviewEvidence = {
  markerName: string;
  value: string;
  referenceRange: string;
  status: 'NORMAL' | 'LOW' | 'HIGH';
  evidenceNote: string;
};

export type DoctorReviewAction = {
  label: string;
  description: string;
  disabled?: boolean;
};

export type DoctorEditedSummaryPreview = {
  originalSummary: string;
  editedSummary: string;
  reviewNote: string;
};

export type DoctorReviewWorkflowStep = {
  title: string;
  description: string;
  status: 'PENDING' | 'CREATED' | 'COMPLETED';
};

export type DoctorReviewOutcomeExample = {
  label: string;
  status: DoctorReviewStatus;
  description: string;
  patientVisibilityImpact: string;
};

export type DoctorReviewNavigationAction = {
  label: string;
  description: string;
  to: string;
};

export type PatientTimelineEvent = {
  title: string;
  eventType: string;
  status: 'PENDING' | 'CREATED' | 'COMPLETED';
  timestamp: string;
  actor: string;
  source: string;
  description: string;
  patientVisibilityImpact: string;
  relatedRoute?: string;
};

export type PatientTimelineStage = {
  name: string;
  description: string;
  status: 'PENDING' | 'CREATED' | 'COMPLETED';
  relatedRoute?: string;
};

export type PatientTimelineAction = {
  label: string;
  description: string;
  to: string;
};

export type DoctorWorklistStatus =
  | 'OPEN'
  | 'IN_REVIEW'
  | 'BLOCKED'
  | 'COMPLETED';

export type DoctorWorklistPriority = 'Low' | 'Medium' | 'High';

export type DoctorWorklistTask = {
  title: string;
  patientName: string;
  taskType: string;
  priority: DoctorWorklistPriority;
  status: DoctorWorklistStatus;
  dueLabel: string;
  assignedRole: string;
  description: string;
  patientVisibilityImpact: string;
  nextReviewStep: string;
  relatedRoute: string;
};

export type DoctorWorklistBucket = {
  name: string;
  taskCount: number;
  status: DoctorWorklistStatus;
  description: string;
  relatedRoute: string;
};

export type DoctorWorklistSlaItem = {
  label: string;
  description: string;
  status: DoctorWorklistStatus;
};

export type DoctorWorklistAction = {
  label: string;
  description: string;
  to?: string;
  disabled?: boolean;
};

export type DoctorWorklistNavigationAction = {
  label: string;
  description: string;
  to: string;
};

export const demoPatient: DemoPatient = {
  name: 'Demo Patient',
  age: 34,
  sex: 'Male',
  patientId: 'demo-patient',
};

export const mockLabResults: LabResult[] = [
  {
    name: 'Hemoglobin',
    value: '14.2 g/dL',
    referenceRange: '13.5-17.5 g/dL',
    status: 'NORMAL',
  },
  {
    name: 'Ferritin',
    value: '14 ng/mL',
    referenceRange: '30-400 ng/mL',
    status: 'LOW',
  },
  {
    name: 'HbA1c',
    value: '6.1%',
    referenceRange: '4.0-5.6%',
    status: 'HIGH',
  },
  {
    name: 'TSH',
    value: '2.4 mIU/L',
    referenceRange: '0.4-4.0 mIU/L',
    status: 'NORMAL',
  },
  {
    name: 'ALT',
    value: '28 U/L',
    referenceRange: '7-56 U/L',
    status: 'NORMAL',
  },
];

export const mockExtractedLabValues: MockExtractedLabValue[] = [
  {
    markerName: 'Hemoglobin',
    extractedValue: '14.2 g/dL',
    referenceRange: '13.5-17.5 g/dL',
    confidence: '98%',
    reviewStatus: 'COMPLETED',
  },
  {
    markerName: 'Ferritin',
    extractedValue: '14 ng/mL',
    referenceRange: '30-400 ng/mL',
    confidence: '96%',
    reviewStatus: 'CREATED',
  },
  {
    markerName: 'HbA1c',
    extractedValue: '6.1%',
    referenceRange: '4.0-5.6%',
    confidence: '95%',
    reviewStatus: 'PENDING',
  },
  {
    markerName: 'TSH',
    extractedValue: '2.4 mIU/L',
    referenceRange: '0.4-4.0 mIU/L',
    confidence: '97%',
    reviewStatus: 'COMPLETED',
  },
  {
    markerName: 'ALT',
    extractedValue: '28 U/L',
    referenceRange: '7-56 U/L',
    confidence: '94%',
    reviewStatus: 'COMPLETED',
  },
];

export const mockAnalysisSteps: MockAnalysisStep[] = [
  {
    title: 'Report staged',
    description: 'The static mock report is staged in the frontend workspace.',
    status: 'COMPLETED',
  },
  {
    title: 'Extraction preview generated',
    description: 'Mock lab values are displayed for structured review.',
    status: 'COMPLETED',
  },
  {
    title: 'Alias matching completed',
    description: 'Marker names are matched to mock canonical labels.',
    status: 'COMPLETED',
  },
  {
    title: 'Reference ranges resolved',
    description: 'Reference range text is prepared for later deterministic labels.',
    status: 'CREATED',
  },
  {
    title: 'Rule engine applied',
    description: 'Mock status labels are shown without backend processing.',
    status: 'CREATED',
  },
  {
    title: 'Review prompts prepared',
    description: 'Flagged structured lab signals are queued as review prompts.',
    status: 'PENDING',
  },
];

export const mockAnalysisActions: MockAnalysisAction[] = [
  {
    label: 'Run mock analysis',
    description: 'Disabled frontend-only action. No backend request is made.',
    disabled: true,
  },
  {
    label: 'View structured results',
    description: 'Open the mock lab result table and deterministic status labels.',
    to: '/analysis/results',
  },
  {
    label: 'Review clinical hypotheses',
    description: 'Open mock physician review prompts prepared from lab signals.',
    to: '/clinical-hypotheses',
  },
  {
    label: 'Open timeline',
    description: 'View the static activity sequence for the mock workflow.',
    to: '/timeline',
  },
];

export const mockAnalysisGroups: AnalysisGroupOverview[] = [
  {
    name: 'Anemia',
    description: 'Red blood cell and iron-related markers grouped for review.',
    markers: ['Hemoglobin', 'Ferritin'],
    flaggedCount: 1,
    reviewStatus: 'CREATED',
  },
  {
    name: 'Diabetes / Prediabetes',
    description: 'Glucose regulation marker staged as a review prompt.',
    markers: ['HbA1c'],
    flaggedCount: 1,
    reviewStatus: 'PENDING',
  },
  {
    name: 'Thyroid',
    description: 'Thyroid marker prepared with deterministic status labeling.',
    markers: ['TSH'],
    flaggedCount: 0,
    reviewStatus: 'COMPLETED',
  },
  {
    name: 'Liver Function',
    description: 'Liver enzyme marker grouped for structured review context.',
    markers: ['ALT'],
    flaggedCount: 0,
    reviewStatus: 'COMPLETED',
  },
];

export const mockAnalysisResultReviewNotes: AnalysisResultReviewNote[] = [
  {
    markerName: 'Hemoglobin',
    note: 'Deterministic NORMAL label in mock data; no review prompt generated.',
  },
  {
    markerName: 'Ferritin',
    note: 'Structured lab signal flagged for physician review.',
  },
  {
    markerName: 'HbA1c',
    note: 'Structured lab signal flagged for physician review.',
  },
  {
    markerName: 'TSH',
    note: 'Deterministic NORMAL label staged for physician review context.',
  },
  {
    markerName: 'ALT',
    note: 'Deterministic NORMAL label staged for physician review context.',
  },
];

export const mockAnalysisTrendPreviews: AnalysisTrendPreview[] = [
  {
    markerName: 'Ferritin',
    direction: 'Down',
    previousValue: '18 ng/mL',
    currentValue: '14 ng/mL',
    note: 'Mock trend preview only. Requires physician review.',
  },
  {
    markerName: 'HbA1c',
    direction: 'Up',
    previousValue: '5.8%',
    currentValue: '6.1%',
    note: 'Mock trend preview only. Requires physician review.',
  },
  {
    markerName: 'TSH',
    direction: 'Stable',
    previousValue: '2.5 mIU/L',
    currentValue: '2.4 mIU/L',
    note: 'Mock trend preview only. Requires physician review.',
  },
];

export const mockAnalysisResultActions: AnalysisResultAction[] = [
  {
    label: 'Review clinical hypotheses',
    description: 'Open review prompts prepared for physician review.',
    to: '/clinical-hypotheses',
  },
  {
    label: 'Open extraction review',
    description: 'Return to the mock extracted value review workspace.',
    to: '/extraction-review',
  },
  {
    label: 'View patient timeline',
    description: 'Review the static sequence for the mock workflow.',
    to: '/timeline',
  },
  {
    label: 'Open demo patient',
    description: 'Open the demo patient workspace with mock report context.',
    to: '/patients/demo',
  },
];

export const mockExtractionJob: MockExtractionJob = {
  fileName: 'lab-report-demo.pdf',
  patientName: 'Demo Patient',
  source: 'Mock upload',
  extractionStatus: 'COMPLETED',
  reviewStatus: 'EDITED',
  createdAt: 'July 3, 2026, 08:12',
  reviewedValuesCount: 4,
};

export const mockExtractionReviewValues: MockExtractionReviewValue[] = [
  {
    markerName: 'Hemoglobin',
    extractedValue: '14.2 g/dL',
    referenceRange: '13.5-17.5 g/dL',
    confidence: '98%',
    reviewStatus: 'APPROVED',
    reviewerNote: 'Marker and value are ready for structured lab signal review.',
    actionState: 'No change requested',
  },
  {
    markerName: 'Ferritin',
    extractedValue: '14 ng/mL',
    referenceRange: '30-400 ng/mL',
    confidence: '96%',
    reviewStatus: 'EDITED',
    reviewerNote: 'Reference range text normalized for the mock workflow.',
    actionState: 'Edited reference text',
  },
  {
    markerName: 'HbA1c',
    extractedValue: '6.1%',
    referenceRange: '4.0-5.6%',
    confidence: '95%',
    reviewStatus: 'PENDING',
    reviewerNote: 'Pending review before analysis continues.',
    actionState: 'Awaiting review',
  },
  {
    markerName: 'TSH',
    extractedValue: '2.4 mIU/L',
    referenceRange: '0.4-4.0 mIU/L',
    confidence: '97%',
    reviewStatus: 'APPROVED',
    reviewerNote: 'Marker name and extracted value are approved in mock data.',
    actionState: 'No change requested',
  },
  {
    markerName: 'ALT',
    extractedValue: '28 U/L',
    referenceRange: '7-56 U/L',
    confidence: '94%',
    reviewStatus: 'REJECTED',
    reviewerNote: 'Row is held for manual confirmation in the mock workflow.',
    actionState: 'Needs re-check',
  },
];

export const mockExtractionReviewActions: MockExtractionReviewAction[] = [
  {
    label: 'Approve selected values',
    description: 'Static control only. No extraction review state is changed.',
    disabled: true,
  },
  {
    label: 'Edit extracted value',
    description: 'Static edit placeholder for the frontend-only review flow.',
    disabled: true,
  },
  {
    label: 'Reject extracted value',
    description: 'Static reject placeholder. No backend request is triggered.',
    disabled: true,
  },
  {
    label: 'Approve and continue to analysis',
    description: 'Open structured results after the mock extraction review.',
    to: '/analysis/results',
  },
];

export const mockTimelineEvents: TimelineEvent[] = [
  {
    title: 'Lab report uploaded',
    status: 'COMPLETED',
    time: '08:10',
  },
  {
    title: 'Extraction job created',
    status: 'CREATED',
    time: '08:12',
  },
  {
    title: 'Analysis completed',
    status: 'COMPLETED',
    time: '08:18',
  },
  {
    title: 'Clinical hypothesis created',
    status: 'CREATED',
    time: '08:21',
  },
  {
    title: 'Doctor review pending',
    status: 'PENDING',
    time: 'Current',
  },
];

export const mockStats: MockStat[] = [
  {
    title: 'Pending reviews',
    value: '12',
    helper: 'Awaiting physician review',
    accent: 'blue',
  },
  {
    title: 'Completed analyses',
    value: '48',
    helper: 'Structured summaries generated',
    accent: 'cyan',
  },
  {
    title: 'Extraction jobs',
    value: '19',
    helper: 'Mock extraction queue items',
    accent: 'slate',
  },
  {
    title: 'Clinical hypotheses',
    value: '7',
    helper: 'Prepared as review prompts',
    accent: 'blue',
  },
];

export const mockClinicalHypotheses: ClinicalHypothesis[] = [
  {
    title: 'Ferritin review prompt',
    observation: 'Ferritin carries a deterministic LOW label in mock results.',
    reviewFocus: 'Review whether additional clinical context is needed.',
    status: 'CREATED',
    priority: 'Medium',
    confidenceLabel: 'Moderate confidence',
    generatedAt: 'July 3, 2026, 08:21',
    source: 'Structured lab analysis mock',
    evidenceMarkers: ['Ferritin'],
  },
  {
    title: 'HbA1c review prompt',
    observation: 'HbA1c carries a deterministic HIGH label in mock results.',
    reviewFocus: 'Review against patient history and current clinical context.',
    status: 'PENDING',
    priority: 'High',
    confidenceLabel: 'Moderate confidence',
    generatedAt: 'July 3, 2026, 08:22',
    source: 'Structured lab analysis mock',
    evidenceMarkers: ['HbA1c'],
  },
];

export const mockClinicalEvidenceSignals: ClinicalEvidenceSignal[] = [
  {
    markerName: 'Ferritin',
    value: '14 ng/mL',
    status: 'LOW',
    relatedHypothesisTitle: 'Ferritin review prompt',
    evidenceNote:
      'Structured lab signal linked to a review prompt. Requires physician review.',
  },
  {
    markerName: 'HbA1c',
    value: '6.1%',
    status: 'HIGH',
    relatedHypothesisTitle: 'HbA1c review prompt',
    evidenceNote:
      'Structured lab signal linked to a review prompt. Requires physician review.',
  },
];

export const mockClinicalReviewActions: ClinicalReviewAction[] = [
  {
    label: 'Approve prompt',
    description: 'Static placeholder only. Doctor approval is not changed.',
    disabled: true,
  },
  {
    label: 'Edit prompt',
    description: 'Static placeholder for adjusting review prompt wording.',
    disabled: true,
  },
  {
    label: 'Request extra test',
    description: 'Static placeholder only. No order or backend request is made.',
    disabled: true,
  },
  {
    label: 'Refer specialist',
    description: 'Static placeholder only. No referral workflow is triggered.',
    disabled: true,
  },
  {
    label: 'Reject prompt',
    description: 'Static placeholder only. No review state is changed.',
    disabled: true,
  },
];

export const mockClinicalReviewWorkflowSteps: ClinicalReviewWorkflowStep[] = [
  {
    title: 'Prompt generated',
    description: 'Mock review prompt is created from structured lab signals.',
    status: 'COMPLETED',
  },
  {
    title: 'Evidence linked',
    description: 'Deterministic lab result labels are attached as evidence.',
    status: 'COMPLETED',
  },
  {
    title: 'Pending doctor review',
    description: 'Prompt remains in the physician review workspace.',
    status: 'PENDING',
  },
  {
    title: 'Doctor action required',
    description: 'A physician must approve, edit, or reject the prompt.',
    status: 'PENDING',
  },
  {
    title: 'Patient-facing content blocked until approval',
    description: 'Patient visibility remains blocked until doctor approval.',
    status: 'CREATED',
  },
];

export const mockClinicalHypothesisNavigationActions: ClinicalHypothesisNavigationAction[] =
  [
    {
      label: 'View analysis results',
      description: 'Open deterministic lab results and structured review notes.',
      to: '/analysis/results',
    },
    {
      label: 'Open extraction review',
      description: 'Inspect the mock extracted values before analysis.',
      to: '/extraction-review',
    },
    {
      label: 'View patient timeline',
      description: 'Review the static mock report activity sequence.',
      to: '/timeline',
    },
    {
      label: 'Open demo patient',
      description: 'Open the demo patient workspace with mock report context.',
      to: '/patients/demo',
    },
    {
      label: 'Open doctor review',
      description: 'Open the mock physician approval workspace.',
      to: '/doctor-review',
    },
  ];

export const mockDoctorReviewCase: DoctorReviewCase = {
  patientName: 'Demo Patient',
  reportName: 'lab-report-demo.pdf',
  reviewStatus: 'PENDING',
  assignedRole: 'Physician reviewer',
  generatedAt: 'July 3, 2026, 08:24',
  pendingActionCount: 2,
  patientVisibilityStatus: 'Blocked until doctor approval',
};

export const mockDoctorReviewPrompt: DoctorReviewPrompt = {
  title: 'Ferritin review prompt',
  observation: 'Ferritin carries a deterministic LOW label in mock results.',
  reviewFocus: 'Review whether additional clinical context is needed.',
  priority: 'Medium',
  confidenceLabel: 'Moderate confidence',
  source: 'Structured lab analysis mock',
  generatedAt: 'July 3, 2026, 08:21',
  evidenceMarkers: ['Ferritin', 'HbA1c'],
};

export const mockDoctorReviewEvidence: DoctorReviewEvidence[] = [
  {
    markerName: 'Ferritin',
    value: '14 ng/mL',
    referenceRange: '30-400 ng/mL',
    status: 'LOW',
    evidenceNote:
      'Structured lab signal linked to a review prompt. Requires physician review.',
  },
  {
    markerName: 'HbA1c',
    value: '6.1%',
    referenceRange: '4.0-5.6%',
    status: 'HIGH',
    evidenceNote:
      'Structured lab signal linked to a review prompt. Requires physician review.',
  },
];

export const mockDoctorReviewActions: DoctorReviewAction[] = [
  {
    label: 'Approve prompt',
    description: 'Approve for physician-reviewed output.',
    disabled: true,
  },
  {
    label: 'Reject prompt',
    description: 'Reject this review prompt.',
    disabled: true,
  },
  {
    label: 'Edit prompt',
    description: 'Edit wording before approval.',
    disabled: true,
  },
  {
    label: 'Request extra test',
    description: 'Request additional test review.',
    disabled: true,
  },
  {
    label: 'Refer specialist',
    description: 'Refer to specialist review.',
    disabled: true,
  },
];

export const mockDoctorEditedSummaryPreview: DoctorEditedSummaryPreview = {
  originalSummary:
    'System-generated review prompt highlights structured lab signals for doctor review.',
  editedSummary:
    'Physician review note preview: structured lab signals should be reviewed with clinical context before any patient-facing wording is approved.',
  reviewNote:
    'This wording is a review-note preview only. Patient-facing content remains blocked until approval.',
};

export const mockDoctorReviewWorkflowSteps: DoctorReviewWorkflowStep[] = [
  {
    title: 'Prompt generated',
    description: 'The mock review prompt is generated from structured signals.',
    status: 'COMPLETED',
  },
  {
    title: 'Evidence attached',
    description: 'Evidence markers are attached for physician review.',
    status: 'COMPLETED',
  },
  {
    title: 'Doctor review pending',
    description: 'The prompt is pending doctor review.',
    status: 'PENDING',
  },
  {
    title: 'Doctor action selected',
    description: 'Action selection is shown as a static placeholder.',
    status: 'CREATED',
  },
  {
    title: 'Patient visibility blocked until approval',
    description: 'Patient-facing content is blocked until approval.',
    status: 'PENDING',
  },
  {
    title: 'Approved content available after physician sign-off',
    description: 'Approved output can be shown only after physician sign-off.',
    status: 'CREATED',
  },
];

export const mockDoctorReviewOutcomeExamples: DoctorReviewOutcomeExample[] = [
  {
    label: 'Approved',
    status: 'APPROVED',
    description: 'Prompt is accepted as physician-reviewed output.',
    patientVisibilityImpact: 'Patient-facing content can become available after sign-off.',
  },
  {
    label: 'Rejected',
    status: 'REJECTED',
    description: 'Prompt is removed from patient-facing consideration.',
    patientVisibilityImpact: 'Patient-facing content remains blocked.',
  },
  {
    label: 'Edited',
    status: 'EDITED',
    description: 'Prompt wording is revised before approval.',
    patientVisibilityImpact: 'Patient-facing content remains blocked until approval.',
  },
  {
    label: 'Extra test requested',
    status: 'EXTRA_TEST_REQUESTED',
    description: 'Additional test review is requested as a placeholder outcome.',
    patientVisibilityImpact: 'Patient-facing content remains blocked.',
  },
  {
    label: 'Specialist referred',
    status: 'SPECIALIST_REFERRED',
    description: 'Specialist review is requested as a placeholder outcome.',
    patientVisibilityImpact: 'Patient-facing content remains blocked.',
  },
];

export const mockDoctorReviewNavigationActions: DoctorReviewNavigationAction[] =
  [
    {
      label: 'Clinical hypotheses',
      description: 'Return to evidence-linked review prompts.',
      to: '/clinical-hypotheses',
    },
    {
      label: 'Analysis results',
      description: 'Open deterministic lab result labels.',
      to: '/analysis/results',
    },
    {
      label: 'Extraction review',
      description: 'Inspect mock extracted values before analysis.',
      to: '/extraction-review',
    },
    {
      label: 'Patient timeline',
      description: 'Review the mock report activity sequence.',
      to: '/timeline',
    },
    {
      label: 'Demo patient',
      description: 'Open the demo patient workspace.',
      to: '/patients/demo',
    },
  ];

export const mockPatientTimelineEvents: PatientTimelineEvent[] = [
  {
    title: 'Lab report uploaded',
    eventType: 'Intake',
    status: 'COMPLETED',
    timestamp: 'July 3, 2026, 08:10',
    actor: 'Mock upload service',
    source: 'lab-report-demo.pdf',
    description: 'Mock lab report was staged for extraction review.',
    patientVisibilityImpact: 'Patient-facing content blocked until approval.',
    relatedRoute: '/patients/demo',
  },
  {
    title: 'Extraction job created',
    eventType: 'Extraction',
    status: 'CREATED',
    timestamp: 'July 3, 2026, 08:12',
    actor: 'Frontend mock workflow',
    source: 'Mock extraction preview',
    description: 'Structured lab values were prepared as static mock data.',
    patientVisibilityImpact: 'No patient-facing content is available.',
    relatedRoute: '/analysis/mock',
  },
  {
    title: 'Extraction review completed',
    eventType: 'Extraction Review',
    status: 'COMPLETED',
    timestamp: 'July 3, 2026, 08:16',
    actor: 'Lab reviewer mock',
    source: 'Extraction review workspace',
    description: 'Mock extracted values were reviewed before analysis.',
    patientVisibilityImpact: 'Patient-facing content remains blocked.',
    relatedRoute: '/extraction-review',
  },
  {
    title: 'Analysis completed',
    eventType: 'Analysis',
    status: 'COMPLETED',
    timestamp: 'July 3, 2026, 08:18',
    actor: 'Deterministic mock rules',
    source: 'Structured analysis results',
    description: 'LOW, NORMAL, and HIGH mock labels were prepared for review.',
    patientVisibilityImpact: 'Results stay in physician review context.',
    relatedRoute: '/analysis/results',
  },
  {
    title: 'Clinical hypothesis created',
    eventType: 'Clinical Review Prompt',
    status: 'CREATED',
    timestamp: 'July 3, 2026, 08:21',
    actor: 'Clinical prompt mock',
    source: 'Clinical hypotheses workspace',
    description: 'Evidence-linked review prompts were created from structured lab signals.',
    patientVisibilityImpact: 'Review prompts are not patient-facing.',
    relatedRoute: '/clinical-hypotheses',
  },
  {
    title: 'Doctor review pending',
    eventType: 'Doctor Review',
    status: 'PENDING',
    timestamp: 'July 3, 2026, 08:24',
    actor: 'Physician reviewer',
    source: 'Doctor review panel',
    description: 'Doctor approval required before any patient-facing content.',
    patientVisibilityImpact: 'Patient-facing content blocked until approval.',
    relatedRoute: '/doctor-review',
  },
  {
    title: 'Doctor review panel opened',
    eventType: 'Doctor Review',
    status: 'CREATED',
    timestamp: 'July 3, 2026, 08:25',
    actor: 'Physician reviewer',
    source: 'Doctor review panel',
    description: 'Static doctor review actions are visible in the mock workflow.',
    patientVisibilityImpact: 'Patient-facing content remains blocked.',
    relatedRoute: '/doctor-review',
  },
  {
    title: 'Patient-facing content blocked until approval',
    eventType: 'Patient Visibility',
    status: 'PENDING',
    timestamp: 'Current',
    actor: 'Safety gate',
    source: 'Mock workflow visibility control',
    description: 'Patient visibility remains blocked until doctor approval.',
    patientVisibilityImpact: 'Doctor approval required before patient visibility.',
    relatedRoute: '/doctor-review',
  },
];

export const mockPatientTimelineStages: PatientTimelineStage[] = [
  {
    name: 'Intake',
    description: 'Mock report staged for the lab-report review workflow.',
    status: 'COMPLETED',
    relatedRoute: '/patients/demo',
  },
  {
    name: 'Extraction Review',
    description: 'Extracted values reviewed before deterministic analysis labels.',
    status: 'COMPLETED',
    relatedRoute: '/extraction-review',
  },
  {
    name: 'Analysis',
    description: 'Structured lab signals prepared with deterministic status labels.',
    status: 'COMPLETED',
    relatedRoute: '/analysis/results',
  },
  {
    name: 'Clinical Review Prompt',
    description: 'Evidence-linked review prompts prepared for physician review.',
    status: 'CREATED',
    relatedRoute: '/clinical-hypotheses',
  },
  {
    name: 'Doctor Review',
    description: 'Doctor approval required before patient-facing content.',
    status: 'PENDING',
    relatedRoute: '/doctor-review',
  },
  {
    name: 'Patient Visibility',
    description: 'Patient-facing content blocked until approval.',
    status: 'PENDING',
  },
];

export const mockPatientTimelineActions: PatientTimelineAction[] = [
  {
    label: 'Demo patient',
    description: 'Open the demo patient workspace.',
    to: '/patients/demo',
  },
  {
    label: 'Mock analysis',
    description: 'Review mock intake and analysis workflow details.',
    to: '/analysis/mock',
  },
  {
    label: 'Extraction review',
    description: 'Inspect extracted lab values before analysis.',
    to: '/extraction-review',
  },
  {
    label: 'Analysis results',
    description: 'Open deterministic lab status labels.',
    to: '/analysis/results',
  },
  {
    label: 'Clinical hypotheses',
    description: 'Open evidence-linked review prompts.',
    to: '/clinical-hypotheses',
  },
  {
    label: 'Doctor review',
    description: 'Open the mock physician approval workspace.',
    to: '/doctor-review',
  },
];

export const mockDoctorWorklistTasks: DoctorWorklistTask[] = [
  {
    title: 'Review clinical hypothesis',
    patientName: 'Demo Patient',
    taskType: 'Clinical hypothesis',
    priority: 'High',
    status: 'OPEN',
    dueLabel: 'Due today',
    assignedRole: 'Physician reviewer',
    description: 'Review task for an evidence-linked prompt pending physician review.',
    patientVisibilityImpact: 'Patient-facing content blocked until approval.',
    nextReviewStep: 'Open clinical hypotheses and review the structured lab signal prompt.',
    relatedRoute: '/clinical-hypotheses',
  },
  {
    title: 'Validate extraction review',
    patientName: 'Demo Patient',
    taskType: 'Extraction review',
    priority: 'Medium',
    status: 'IN_REVIEW',
    dueLabel: 'Due today',
    assignedRole: 'Physician reviewer',
    description: 'Review task for mock extracted values before downstream review.',
    patientVisibilityImpact: 'Clinical content remains blocked.',
    nextReviewStep: 'Open extraction review and confirm reviewed mock values.',
    relatedRoute: '/extraction-review',
  },
  {
    title: 'Review abnormal lab signals',
    patientName: 'Demo Patient',
    taskType: 'Analysis result',
    priority: 'Medium',
    status: 'OPEN',
    dueLabel: 'Due today',
    assignedRole: 'Physician reviewer',
    description: 'Review structured lab signal labels flagged for physician review.',
    patientVisibilityImpact: 'Patient-facing content blocked until approval.',
    nextReviewStep: 'Open analysis results and review deterministic status labels.',
    relatedRoute: '/analysis/results',
  },
  {
    title: 'Complete doctor approval',
    patientName: 'Demo Patient',
    taskType: 'Doctor review',
    priority: 'High',
    status: 'BLOCKED',
    dueLabel: 'Needs doctor approval',
    assignedRole: 'Physician reviewer',
    description: 'Doctor approval required before patient-facing content can proceed.',
    patientVisibilityImpact: 'Patient-facing content blocked until approval.',
    nextReviewStep: 'Open doctor review and complete the static approval workflow.',
    relatedRoute: '/doctor-review',
  },
  {
    title: 'Check patient timeline',
    patientName: 'Demo Patient',
    taskType: 'Timeline review',
    priority: 'Low',
    status: 'OPEN',
    dueLabel: 'Review prompt waiting',
    assignedRole: 'Physician reviewer',
    description: 'Review task for the mock task queue and timeline event sequence.',
    patientVisibilityImpact: 'Clinical content remains blocked.',
    nextReviewStep: 'Open patient timeline and confirm mock workflow context.',
    relatedRoute: '/timeline',
  },
];

export const mockDoctorWorklistBuckets: DoctorWorklistBucket[] = [
  {
    name: 'Extraction Review',
    taskCount: 1,
    status: 'IN_REVIEW',
    description: 'Mock extracted values waiting for review completion.',
    relatedRoute: '/extraction-review',
  },
  {
    name: 'Analysis Results',
    taskCount: 1,
    status: 'OPEN',
    description: 'Structured lab signal labels pending physician review.',
    relatedRoute: '/analysis/results',
  },
  {
    name: 'Clinical Hypotheses',
    taskCount: 1,
    status: 'OPEN',
    description: 'Evidence-linked review prompt waiting for physician review.',
    relatedRoute: '/clinical-hypotheses',
  },
  {
    name: 'Doctor Review',
    taskCount: 1,
    status: 'BLOCKED',
    description: 'Doctor approval required before patient-facing content.',
    relatedRoute: '/doctor-review',
  },
  {
    name: 'Timeline Follow-up',
    taskCount: 1,
    status: 'OPEN',
    description: 'Mock workflow event sequence ready for review.',
    relatedRoute: '/timeline',
  },
];

export const mockDoctorWorklistSlaItems: DoctorWorklistSlaItem[] = [
  {
    label: 'Due today',
    description: 'Review task is visible in the mock task queue.',
    status: 'OPEN',
  },
  {
    label: 'Needs doctor approval',
    description: 'Doctor approval required before patient-facing content.',
    status: 'BLOCKED',
  },
  {
    label: 'Patient visibility blocked',
    description: 'Patient-facing content blocked until approval.',
    status: 'BLOCKED',
  },
  {
    label: 'Review prompt waiting',
    description: 'Evidence-linked prompt is pending physician review.',
    status: 'OPEN',
  },
];

export const mockDoctorWorklistActions: DoctorWorklistAction[] = [
  {
    label: 'Open selected task',
    description: 'Open the doctor review page for the selected mock task.',
    to: '/doctor-review',
  },
  {
    label: 'Mark as in review',
    description: 'Static placeholder only. No task status is changed.',
    disabled: true,
  },
  {
    label: 'Request more context',
    description: 'Static placeholder only. No backend request is made.',
    disabled: true,
  },
  {
    label: 'Complete review',
    description: 'Static placeholder only. No clinical content is approved.',
    disabled: true,
  },
  {
    label: 'Defer task',
    description: 'Static placeholder only. No scheduling is changed.',
    disabled: true,
  },
];

export const mockDoctorWorklistNavigationActions: DoctorWorklistNavigationAction[] =
  [
    {
      label: 'Doctor review',
      description: 'Open the mock physician approval workspace.',
      to: '/doctor-review',
    },
    {
      label: 'Clinical hypotheses',
      description: 'Open evidence-linked review prompts.',
      to: '/clinical-hypotheses',
    },
    {
      label: 'Extraction review',
      description: 'Inspect mock extracted lab values.',
      to: '/extraction-review',
    },
    {
      label: 'Analysis results',
      description: 'Open deterministic lab status labels.',
      to: '/analysis/results',
    },
    {
      label: 'Patient timeline',
      description: 'Review mock workflow activity.',
      to: '/timeline',
    },
    {
      label: 'Demo patient',
      description: 'Open the demo patient workspace.',
      to: '/patients/demo',
    },
  ];

export const mockDashboardQueue: DashboardQueueItem[] = [
  {
    patientName: 'Demo Patient',
    type: 'Clinical hypothesis',
    priority: 'Medium',
    status: 'PENDING',
    description: 'Pending doctor review',
  },
  {
    patientName: 'Demo Patient',
    type: 'Extraction review',
    priority: 'Low',
    status: 'CREATED',
    description: 'Ready for review',
  },
  {
    patientName: 'Demo Patient',
    type: 'Analysis result',
    priority: 'Medium',
    status: 'PENDING',
    description: 'Abnormal values flagged for physician review',
  },
];

export const mockQuickActions: QuickAction[] = [
  {
    label: 'Review pending hypotheses',
    description: 'Open physician review prompts for the demo workflow.',
    to: '/clinical-hypotheses',
  },
  {
    label: 'Open extraction review',
    description: 'Review mock extraction status and extracted lab signals.',
    to: '/extraction-review',
  },
  {
    label: 'View analysis results',
    description: 'Inspect structured mock result values and status flags.',
    to: '/analysis/results',
  },
  {
    label: 'Open patient timeline',
    description: 'Follow the mock report activity sequence.',
    to: '/timeline',
  },
];

export const mockPatientReportSummary: PatientReportSummary = {
  reportName: 'lab-report-demo.pdf',
  uploadedAt: 'July 3, 2026, 08:10',
  extractionStatus: 'COMPLETED',
  analysisStatus: 'COMPLETED',
  hypothesisStatus: 'CREATED',
  doctorReviewStatus: 'PENDING',
};

export const mockPatientShortcuts: PatientShortcut[] = [
  {
    label: 'View analysis results',
    description: 'Open structured lab signal results for physician review.',
    to: '/analysis/results',
  },
  {
    label: 'Review hypotheses',
    description: 'Review mock clinical prompts prepared for doctor review.',
    to: '/clinical-hypotheses',
  },
  {
    label: 'Open mock analysis',
    description: 'Inspect extraction and analysis workflow details.',
    to: '/analysis/mock',
  },
  {
    label: 'View timeline',
    description: 'Review the demo report activity sequence.',
    to: '/timeline',
  },
];
