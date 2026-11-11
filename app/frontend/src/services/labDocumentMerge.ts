import type { LabInput, LabOutput } from './simpleCaseClient';

function clearClassification(lab: LabInput) {
  // Legacy rows may retain their only printed reference in raw_reference.
  if (!lab.source_reference && !(lab.source_references ?? []).length && lab.raw_reference) {
    lab.source_reference = lab.raw_reference;
  }
  delete lab.status; delete lab.reference_low; delete lab.reference_high;
  delete lab.raw_reference; delete lab.classification_reason;
  delete lab.normalized_value; delete lab.value_comparator; delete lab.value_limit; delete lab.parsed_unit;
}


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
  if (!(lab.source_references ?? []).some((ref) => ref.age_min != null || ref.age_max != null || (ref.sex && ref.sex !== 'unknown'))) return lab;
  const input = { ...lab };
  clearClassification(input);
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
      reference: row.source_reference || (!(row.source_references ?? []).length ? row.raw_reference : null), references: (row.source_references ?? []).map((ref) => JSON.stringify(Object.fromEntries(Object.entries(ref).sort(([a],[b]) => a.localeCompare(b))))).sort(), flag: row.source_metadata?.source_flag ?? null,
      document: dated ? null : sha,
    });
    const duplicate = seen.get(key);
    if (!duplicate) {
      const copy = { ...row, source_metadata: { ...row.source_metadata } };
      seen.set(key, copy); output.push(copy); continue;
    }
    const classificationEvidence = duplicate.status ? duplicate.source_metadata : row.source_metadata;
    const derivedConflict = (['status', 'reference_low', 'reference_high', 'raw_reference', 'classification_reason',
      'normalized_value', 'value_comparator', 'value_limit', 'parsed_unit'] as const).some((field) =>
      duplicate[field] != null && row[field] != null && duplicate[field] !== row[field]);
    if (derivedConflict) {
      // Conflicting canonical readings require server revalidation after merging.
      invalidatedStatuses.add(key);
      clearClassification(duplicate);
    } else if (!duplicate.status && row.status && !invalidatedStatuses.has(key)) {
      duplicate.status = row.status;
      duplicate.reference_low = row.reference_low;
      duplicate.reference_high = row.reference_high;
      duplicate.raw_reference = row.raw_reference;
      duplicate.classification_reason = row.classification_reason;
      duplicate.normalized_value = row.normalized_value;
      duplicate.value_comparator = row.value_comparator;
      duplicate.value_limit = row.value_limit;
      duplicate.parsed_unit = row.parsed_unit;
    }
    const sources = [
      ...(Array.isArray(duplicate.source_metadata?.source_documents) ? duplicate.source_metadata.source_documents : []),
      ...(Array.isArray(row.source_metadata?.source_documents) ? row.source_metadata.source_documents : []),
      { file: duplicate.source_metadata?.source_file_name, sha: duplicate.source_metadata?.source_sha256 },
      { file: row.source_metadata?.source_file_name, sha },
    ];
    const previousReasons = JSON.stringify([...(Array.isArray(classificationEvidence?.ingestion_reasons) ? classificationEvidence.ingestion_reasons : [])].sort());
    const previousReview = Boolean(classificationEvidence?.needs_review);
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
    const mergedReasons = JSON.stringify([...(duplicate.source_metadata.ingestion_reasons as string[])].sort());
    if (previousReasons !== mergedReasons || previousReview !== Boolean(duplicate.source_metadata.needs_review)) {
      invalidatedStatuses.add(key);
      clearClassification(duplicate);
    }
  }
  return output;
}
