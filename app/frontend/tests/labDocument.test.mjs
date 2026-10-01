import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyLabForDisplay } from '../src/services/labDisplayClassification.ts';
import { mergeLabDocuments } from '../src/services/labDocumentMerge.ts';
function row(value, reference = '2 - 5', extra = {}) {
  return { test_name: 'TSH', value, unit: null, source_reference: reference, source_references: [], ...extra };
}
test('normal, high, low and zero use source bounds only', () => {
  assert.equal(classifyLabForDisplay(row(3)).status, 'normal');
  assert.equal(classifyLabForDisplay(row(6)).direction, 'high');
  assert.equal(classifyLabForDisplay(row(0)).direction, 'low');
  assert.equal(classifyLabForDisplay(row(0, '0 - 5')).status, 'normal');
});
test('source flags are copied; stale backend grouping cannot override changed values', () => {
  assert.equal(classifyLabForDisplay(row(3, null, { source_metadata: { source_flag: 'Yüksek' } })).direction, 'high');
  assert.equal(classifyLabForDisplay(row(8, '2 - 5', { source_metadata: { display_status: 'normal' } })).direction, 'high');
});
test('inequality boundary equality respects inclusive limits', () => {
  assert.equal(classifyLabForDisplay(row('<=2')).status, 'unclassified');
  assert.equal(classifyLabForDisplay(row('<2')).direction, 'low');
  assert.equal(classifyLabForDisplay(row('>=5')).status, 'unclassified');
  assert.equal(classifyLabForDisplay(row('>5')).direction, 'high');
  assert.equal(classifyLabForDisplay(row(5, '<5')).direction, 'high');
  assert.equal(classifyLabForDisplay(row(5, '<=5')).status, 'normal');
});
test('missing, reversed, ambiguous and incompatible-unit references stay unclassified', () => {
  assert.equal(classifyLabForDisplay(row(3, null)).status, 'unclassified');
  assert.equal(classifyLabForDisplay(row(3, '5 - 2')).status, 'unclassified');
  assert.equal(classifyLabForDisplay(row(3, 'Adult: 2 - 5')).status, 'unclassified');
  assert.equal(classifyLabForDisplay(row(3, '2 - 5 mg/L', { unit: 'mg/dL' })).status, 'unclassified');
});
test('conflicting transcription is never labeled normal', () => {
  assert.equal(classifyLabForDisplay(row(3, '2 - 5', { source_metadata: { ingestion_reasons: ['conflicting_or_repeated_observation'], source_flag: 'Normal' } })).status, 'unclassified');
});
test('re-upload deduplication preserves different dates, documents and statuses', () => {
  const first = row(3, '2 - 5', { source_metadata: { source_sha256: 'same', source_flag: 'Normal' } });
  assert.equal(mergeLabDocuments([first], [structuredClone(first)]).length, 1);
  assert.equal(mergeLabDocuments([first], [row(3, '2 - 5', { source_metadata: { source_sha256: 'other' } })]).length, 2);
  assert.equal(mergeLabDocuments([first], [{ ...first, measured_at: '2026-10-01' }]).length, 2);
  assert.equal(mergeLabDocuments([first], [{ ...first, source_metadata: { source_sha256: 'same', source_flag: 'High' } }]).length, 2);
});
