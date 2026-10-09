import type { PatientRecord } from './patientClient';

/** Older records need no backfill: the existing protocol is their display name. */
export function caseDisplayName(record: Pick<PatientRecord, 'protocol_no' | 'metadata_json' | 'case_name'>): string {
  const stored = record.case_name ?? record.metadata_json?.case_name;
  return typeof stored === 'string' && stored.trim() ? stored.trim() : record.protocol_no;
}

export function normalizeCaseName(value: string): string {
  return value.trim().normalize('NFKC').toLowerCase().replace(/ß/g, 'ss').replace(/ς/g, 'σ');
}

export function caseNameMatches(record: PatientRecord, query: string): boolean {
  return normalizeCaseName(caseDisplayName(record)).includes(normalizeCaseName(query));
}
