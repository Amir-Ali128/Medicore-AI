import { apiClient } from './apiClient';

export type ClinicalContext = {
  age: number | null;
  sex: 'female' | 'male' | 'other' | 'unknown';
  complaints: string[];
  history: string[];
  medications: string[];
  notes: string | null;
};

export type LabReference = {
  text: string;
  minimum?: number | null;
  maximum?: number | null;
  unit?: string | null;
  age_min?: number | null;
  age_max?: number | null;
  sex?: 'female' | 'male' | 'other' | 'unknown' | null;
};

export type LabInput = {
  test_name: string;
  value: string | number | null;
  unit: string | null;
  source_reference: string | null;
  source_references: LabReference[];
};

export type MedicalReportInput = {
  report_type: string;
  body_region: string | null;
  findings: string | null;
  impression: string | null;
  raw_text: string | null;
};

export type SimpleCaseRequest = {
  clinical: ClinicalContext;
  labs: LabInput[];
  reports: MedicalReportInput[];
};

export type SimpleCaseResponse = {
  contract_version: 'medicore-simple-case-v1';
  clinical: ClinicalContext;
  labs: Array<{
    test_name: string;
    value: string | number | null;
    unit: string | null;
    reference_text: string | null;
    reference_source: 'report' | 'report_age_sex_match' | 'missing';
  }>;
  reports: MedicalReportInput[];
  warnings: string[];
};

export function normalizeSimpleCase(payload: SimpleCaseRequest) {
  return apiClient.post<SimpleCaseResponse>('/simple-case/normalize', payload);
}
