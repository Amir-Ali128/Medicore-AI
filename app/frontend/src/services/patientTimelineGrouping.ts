import type { ClinicalContext, VitalSigns } from './simpleCaseClient';

export type TimelineDates = {
  event_date?: string | null; specimen_date?: string | null; result_date?: string | null;
  document_date?: string | null; uploaded_at?: string | null;
  exam_date?: string | null; consultation_date?: string | null;
};
export type TimelineLabValue = TimelineDates & {
  id: string; test_name: string; value: string | number | null; unit: string | null; reference_text: string | null;
  status?: 'LOW' | 'NORMAL' | 'HIGH' | 'UNKNOWN';
  reference_low?: number | null; reference_high?: number | null; raw_reference?: string | null;
};
export type PatientTimelineEntry = TimelineDates & {
  id: string; patient_id: string;
  kind: 'laboratory' | 'urine_laboratory' | 'lab_result_available' | 'report' | 'clinical' | 'vital_signs';
  source_type: 'lab_report' | 'radiology_report' | 'patient'; source_id: string; source_path: string | null;
  title: string; date_source: string; results: TimelineLabValue[]; result_ids?: string[];
  clinical: ClinicalContext | null; vital_signs: VitalSigns | null;
  inferred_report_type: string | null; report_type_confidence: number | null;
  report_text: string | null; summary: string | null; file_name: string | null;
  original_file_available: boolean;
};
export type PatientTimelineDay = { date: string | null; entries: PatientTimelineEntry[] };
export type PatientHealthTimeline = { patient_id: string; groups: PatientTimelineDay[]; total_entries: number; total_lab_results: number };

/** Fail closed before rendering an API response for a different selection. */
export function groupPatientTimeline(response: PatientHealthTimeline, patientId: string): PatientTimelineDay[] {
  if (response.patient_id !== patientId) throw new Error('Hasta geçmişi seçili hastayla eşleşmiyor.');
  const groups = new Map<string | null, PatientTimelineEntry[]>();
  for (const group of response.groups) {
    for (const entry of group.entries) {
      if (entry.patient_id !== patientId) throw new Error('Geçmiş kaydı seçili hastayla eşleşmiyor.');
      const entries = groups.get(group.date) ?? [];
      entries.push(entry);
      groups.set(group.date, entries);
    }
  }
  return [...groups].sort(([first], [second]) => {
    if (first === second) return 0;
    if (first === null) return 1;
    if (second === null) return -1;
    return second.localeCompare(first);
  }).map(([date, entries]) => ({ date, entries }));
}

const REPORT_LABELS: Record<string, string> = {
  CT: 'BT / Tomografi', ULTRASOUND: 'Ultrason / USG', MRI: 'MR', X_RAY: 'Röntgen',
  PATHOLOGY: 'Patoloji', ECHOCARDIOGRAPHY: 'Ekokardiyografi', ENDOSCOPY: 'Endoskopi',
  OTHER: 'Diğer Rapor', UNKNOWN: 'Rapor',
};
export function timelineReportLabel(type: string | null): string {
  return REPORT_LABELS[type ?? 'UNKNOWN'] ?? 'Rapor';
}
