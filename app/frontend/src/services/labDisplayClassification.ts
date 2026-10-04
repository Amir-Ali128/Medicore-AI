import type { CanonicalLabClassification } from './simpleCaseClient';

export type LabDisplayClassification = {
  status: 'normal' | 'abnormal' | 'unclassified';
  direction: 'low' | 'high' | null;
};

// Numeric references and transcription uncertainty are evaluated by the backend.
// Printed source flags remain document annotations, not classification authority.
export function classifyLabForDisplay(lab: CanonicalLabClassification): LabDisplayClassification {
  switch (lab.status) {
    case 'NORMAL': return { status: 'normal', direction: null };
    case 'LOW': return { status: 'abnormal', direction: 'low' };
    case 'HIGH': return { status: 'abnormal', direction: 'high' };
    default: return { status: 'unclassified', direction: null };
  }
}
