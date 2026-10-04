import type { LabInput, LabOutput } from './simpleCaseClient';

// Preserve server classification and date fields when restoring or saving a case.
export function normalizedLabToInput(item: LabOutput): LabInput {
  const { reference_text, reference_source: _source, reference_details, ...row } = item;
  return {
    ...row,
    source_reference: 'source_reference' in item ? item.source_reference ?? null : reference_text,
    source_references: item.source_references ?? (reference_details ? [reference_details] : []),
    source_metadata: item.source_metadata ?? {},
  };
}

export function invalidateDemographicClassification(lab: LabInput): LabInput {
  if (!lab.source_references.some((ref) => ref.age_min != null || ref.age_max != null || (ref.sex && ref.sex !== 'unknown'))) return lab;
  const { status: _status, reference_low: _low, reference_high: _high,
    raw_reference: _reference, classification_reason: _reason, ...input } = lab;
  return input;
}

export function mergeLabDocuments(existing: LabInput[], incoming: LabInput[]): LabInput[] {
  const output: LabInput[] = [];
  const seen = new Map<string, LabInput>();
  const invalidatedStatuses = new Set<string>();
  for (const row of [...existing, ...incoming]) {
    const sha = row.source_metadata?.source_sha256;
    const dated = Boolean(row.specimen_date || row.event_date || row.measured_at || row.document_date || row.result_date);
    // Undated values from different documents may be separate observations.
    if (!sha && !dated) { output.push(row); continue; }
    const key = JSON.stringify({
      name: row.source_metadata?.raw_parameter_name ?? row.test_name,
      value: row.value, unit: row.unit, date: row.measured_at ?? null,
      event_date: row.event_date ?? null, specimen_date: row.specimen_date ?? null,
      result_date: row.result_date ?? null, document_date: row.document_date ?? null,
      reference: row.source_reference, references: row.source_references.map((ref) => JSON.stringify(Object.fromEntries(Object.entries(ref).sort(([a],[b]) => a.localeCompare(b))))), flag: row.source_metadata?.source_flag ?? null,
      document: dated ? null : sha,
    });
    const duplicate = seen.get(key);
    if (!duplicate) {
      const copy = { ...row, source_metadata: { ...row.source_metadata } };
      seen.set(key, copy); output.push(copy); continue;
    }
    if (duplicate.status && row.status && duplicate.status !== row.status) {
      // Conflicting canonical readings require server revalidation after merging.
      invalidatedStatuses.add(key);
      delete duplicate.status;
      delete duplicate.classification_reason;
    } else if (!duplicate.status && row.status && !invalidatedStatuses.has(key)) {
      duplicate.status = row.status;
      duplicate.reference_low = row.reference_low;
      duplicate.reference_high = row.reference_high;
      duplicate.raw_reference = row.raw_reference;
      duplicate.classification_reason = row.classification_reason;
    }
    const sources = [
      ...(Array.isArray(duplicate.source_metadata?.source_documents) ? duplicate.source_metadata.source_documents : []),
      ...(Array.isArray(row.source_metadata?.source_documents) ? row.source_metadata.source_documents : []),
      { file: duplicate.source_metadata?.source_file_name, sha: duplicate.source_metadata?.source_sha256 },
      { file: row.source_metadata?.source_file_name, sha },
    ];
    duplicate.source_metadata = {
      ...duplicate.source_metadata,
      source_documents: sources.filter((item, index) => sources.findIndex((other) => JSON.stringify(item) === JSON.stringify(other)) === index),
      needs_review: Boolean(duplicate.source_metadata?.needs_review || row.source_metadata?.needs_review),
      ingestion_reasons: [...new Set([
        ...(Array.isArray(duplicate.source_metadata?.ingestion_reasons) ? duplicate.source_metadata.ingestion_reasons : []),
        ...(Array.isArray(row.source_metadata?.ingestion_reasons) ? row.source_metadata.ingestion_reasons : []),
      ])],
      document_warnings: [...new Set([
        ...(Array.isArray(duplicate.source_metadata?.document_warnings) ? duplicate.source_metadata.document_warnings : []),
        ...(Array.isArray(row.source_metadata?.document_warnings) ? row.source_metadata.document_warnings : []),
      ])],
    };
  }
  return output;
}
