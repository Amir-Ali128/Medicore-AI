import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyLabForDisplay } from '../src/services/labDisplayClassification.ts';
import { invalidateDemographicClassification, mergeLabDocuments, normalizedLabToInput } from '../src/services/labDocumentMerge.ts';
function row(value, reference = '2 - 5', extra = {}) {
  return { test_name: 'TSH', value, unit: null, source_reference: reference, source_references: [], ...extra };
}
test('display maps the four authoritative backend statuses', () => {
  assert.deepEqual(classifyLabForDisplay(row(3, '2 - 5', { status: 'NORMAL' })), { status: 'normal', direction: null });
  assert.deepEqual(classifyLabForDisplay(row(6, '2 - 5', { status: 'HIGH' })), { status: 'abnormal', direction: 'high' });
  assert.deepEqual(classifyLabForDisplay(row(0, '2 - 5', { status: 'LOW' })), { status: 'abnormal', direction: 'low' });
  assert.deepEqual(classifyLabForDisplay(row(3, '2 - 5', { status: 'UNKNOWN' })), { status: 'unclassified', direction: null });
});
test('TIBC 445 stays normal even when the document prints a High flag', () => {
  const tibc = row(445, '250 – 450', { test_name: 'TIBC', status: 'NORMAL', reference_low: 250, reference_high: 450,
    source_metadata: { source_flag: 'High', display_status: 'abnormal' } });
  assert.deepEqual(classifyLabForDisplay(tibc), { status: 'normal', direction: null });
  assert.equal(classifyLabForDisplay({ ...tibc, status: 'LOW', source_metadata: { source_flag: 'Normal' } }).direction, 'low');
});
test('old or unclassified rows are not classified from numbers, flags or metadata', () => {
  for (const value of [3, 8, '3,2', '<2', '>200', 'Pozitif']) {
    assert.equal(classifyLabForDisplay(row(value)).status, 'unclassified');
    assert.equal(classifyLabForDisplay(row(value, null, { source_metadata: { source_flag: 'Yüksek', display_status: 'normal' } })).status, 'unclassified');
  }
  assert.equal(classifyLabForDisplay(row(8, '2 - 5', { status: 'invalid' })).status, 'unclassified');
});
test('ambiguous censored and qualitative readings keep server UNKNOWN', () => {
  for (const value of ['<=2', '>=5', 'Pozitif']) {
    assert.equal(classifyLabForDisplay(row(value, '2 - 5', { status: 'UNKNOWN' })).status, 'unclassified');
  }
  assert.equal(classifyLabForDisplay(row('<2', '2 - 5', { status: 'LOW' })).direction, 'low');
});
test('re-upload deduplication preserves different dates, documents and source flags', () => {
  const first = row(3, '2 - 5', { source_metadata: { source_sha256: 'same', source_flag: 'Normal' } });
  assert.equal(mergeLabDocuments([first], [structuredClone(first)]).length, 1);
  assert.equal(mergeLabDocuments([first], [row(3, '2 - 5', { source_metadata: { source_sha256: 'other' } })]).length, 2);
  assert.equal(mergeLabDocuments([first], [{ ...first, measured_at: '2026-10-01' }]).length, 2);
  assert.equal(mergeLabDocuments([first], [{ ...first, source_metadata: { source_sha256: 'same', source_flag: 'High' } }]).length, 2);
});
test('merging preserves separate specimen and result dates and ignores re-upload time', () => {
  const first = row(5, '15 — 150', { test_name: 'Ferritin', status: 'LOW', specimen_date: '2026-10-02',
    result_date: '2026-10-04', uploaded_at: '2026-10-04T10:00:00Z', source_metadata: { source_sha256: 'same' } });
  const merged = mergeLabDocuments([first], [{ ...first, uploaded_at: '2026-10-05T10:00:00Z' }]);
  assert.equal(merged.length, 1);
  assert.equal(merged[0].status, 'LOW');
  assert.equal(merged[0].specimen_date, '2026-10-02');
  assert.equal(merged[0].result_date, '2026-10-04');
  assert.equal(mergeLabDocuments([first], [{ ...first, result_date: '2026-10-03' }]).length, 2);
  assert.equal(mergeLabDocuments([first], [{ ...first, specimen_date: '2026-10-01' }]).length, 2);
});
test('re-upload keeps review reasons and document warnings from both readings', () => {
  const first = row(3, '2 - 5', { status: 'NORMAL', source_metadata: { source_sha256: 'same' } });
  const second = row(3, '2 - 5', { status: 'UNKNOWN', source_metadata: { source_sha256: 'same', needs_review: true,
    ingestion_reasons: ['low_input_confidence'], document_warnings: ['page_2:blurred_image'] } });
  const merged = mergeLabDocuments([first], [second]);
  assert.equal(merged.length, 1);
  assert.equal(merged[0].source_metadata.needs_review, true);
  assert.deepEqual(merged[0].source_metadata.document_warnings, ['page_2:blurred_image']);
  assert.equal(merged[0].status, undefined);
  assert.equal(classifyLabForDisplay(merged[0]).status, 'unclassified');
  const repeated = mergeLabDocuments([first], [second, structuredClone(first)]);
  assert.equal(repeated.length, 1);
  assert.equal(classifyLabForDisplay(repeated[0]).status, 'unclassified');
});
test('hydrated and saved rows retain canonical status, bounds and every semantic date', () => {
  const saved = { test_name: 'TIBC', value: 445, unit: 'µg/dL', reference_text: '250 – 450', reference_source: 'report',
    reference_details: { text: '250 – 450', minimum: 250, maximum: 450 },
    status: 'NORMAL', reference_low: 250, reference_high: 450, raw_reference: '250 – 450', classification_reason: 'within_reference',
    measured_at: '2026-10-02', event_date: '2026-10-02', specimen_date: '2026-10-02', result_date: '2026-10-04',
    document_date: '2026-10-04', uploaded_at: '2026-10-04T10:00:00Z', source_metadata: { source_sha256: 'same', source_flag: 'High' } };
  const restored = normalizedLabToInput(saved);
  for (const key of ['status', 'reference_low', 'reference_high', 'raw_reference', 'classification_reason',
    'measured_at', 'event_date', 'specimen_date', 'result_date', 'document_date', 'uploaded_at']) {
    assert.equal(restored[key], saved[key], key);
  }
  assert.equal(restored.source_reference, saved.reference_text);
  assert.deepEqual(restored.source_references, [saved.reference_details]);
  assert.deepEqual(classifyLabForDisplay(restored), { status: 'normal', direction: null });
});

test('selected reference never replaces the complete original demographic reference set', () => {
  const refs = [{ text: '12 – 16', minimum: 12, maximum: 16, sex: 'female' },
    { text: '13 – 17', minimum: 13, maximum: 17, sex: 'male' }];
  const saved = { test_name: 'Hb', value: 16.5, unit: 'g/dL', status: 'HIGH', reference_low: 12, reference_high: 16,
    raw_reference: '12 – 16', reference_text: '12 – 16', reference_source: 'report_age_sex_match',
    reference_details: refs[0], source_reference: null, source_references: refs };
  const restored = normalizedLabToInput(saved);
  assert.equal(restored.source_reference, null);
  assert.deepEqual(restored.source_references, refs);
  assert.equal(restored.raw_reference, saved.reference_text);
  const edited = invalidateDemographicClassification(restored);
  assert.equal(classifyLabForDisplay(edited).status, 'unclassified');
  assert.deepEqual(edited.source_references, refs);
  assert.equal(edited.value, 16.5);
  const generic = row(445, '250 – 450', { status: 'NORMAL' });
  assert.equal(invalidateDemographicClassification(generic), generic);
});
