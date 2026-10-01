import type { LabInput } from './simpleCaseClient';

export function mergeLabDocuments(existing: LabInput[], incoming: LabInput[]): LabInput[] {
  const output: LabInput[] = [];
  const seen = new Map<string, LabInput>();
  for (const row of [...existing, ...incoming]) {
    const sha = row.source_metadata?.source_sha256;
    // Undated values from different documents may be separate observations.
    if (!sha && !row.measured_at) { output.push(row); continue; }
    const key = JSON.stringify({
      name: row.source_metadata?.raw_parameter_name ?? row.test_name,
      value: row.value, unit: row.unit, date: row.measured_at ?? null,
      reference: row.source_reference, references: row.source_references.map((ref) => JSON.stringify(Object.fromEntries(Object.entries(ref).sort(([a],[b]) => a.localeCompare(b))))), flag: row.source_metadata?.source_flag ?? null,
      document: row.measured_at ? null : sha,
    });
    const duplicate = seen.get(key);
    if (!duplicate) {
      const copy = { ...row, source_metadata: { ...row.source_metadata } };
      seen.set(key, copy); output.push(copy); continue;
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
