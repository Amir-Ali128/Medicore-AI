import { apiClient } from './apiClient';
import { groupPatientTimeline, type PatientHealthTimeline } from './patientTimelineGrouping';

export async function getPatientHealthTimeline(patientId: string, signal?: AbortSignal): Promise<PatientHealthTimeline> {
  const response = await apiClient.get<PatientHealthTimeline>(
    `/timeline/patients/${encodeURIComponent(patientId)}/health-history`, { signal },
  );
  // Check before any component stores or renders the response.
  return { ...response, groups: groupPatientTimeline(response, patientId) };
}
