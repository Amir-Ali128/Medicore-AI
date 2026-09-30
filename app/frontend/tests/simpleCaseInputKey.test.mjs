import assert from 'node:assert/strict';
import test from 'node:test';
import { simpleCaseInputKey } from '../src/services/simpleCaseInputKey.ts';

function caseData() {
  return {
    clinical: { age: 40, sex: 'unknown', complaints: ['fatigue'], notes: null },
    labs: [{ test_name: 'TSH', value: 2.1, source_metadata: { page: 1, file: 'lab.pdf' } }],
    reports: [],
  };
}

function reverseObjectFields(value) {
  if (Array.isArray(value)) return value.map(reverseObjectFields);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).reverse().map(([key, item]) => [key, reverseObjectFields(item)]),
    );
  }
  return value;
}

test('saved JSON with different field order keeps the same AI input key', () => {
  const payload = caseData();
  assert.equal(simpleCaseInputKey('patient-1', payload), simpleCaseInputKey('patient-1', reverseObjectFields(payload)));
});

test('changing a clinical or laboratory value invalidates the old AI input key', () => {
  const payload = caseData();
  const original = simpleCaseInputKey('patient-1', payload);
  const clinicalEdit = structuredClone(payload);
  clinicalEdit.clinical.age = 45;
  assert.notEqual(simpleCaseInputKey('patient-1', clinicalEdit), original);
  const labEdit = structuredClone(payload);
  labEdit.labs[0].value = 4.2;
  assert.notEqual(simpleCaseInputKey('patient-1', labEdit), original);
});

test('switching patients invalidates a late AI response for the previous patient', () => {
  const payload = caseData();
  assert.notEqual(simpleCaseInputKey('patient-1', payload), simpleCaseInputKey('patient-2', payload));
});

test('array order remains significant', () => {
  const payload = caseData();
  payload.clinical.complaints = ['fatigue', 'cough'];
  const original = simpleCaseInputKey('patient-1', payload);
  payload.clinical.complaints.reverse();
  assert.notEqual(simpleCaseInputKey('patient-1', payload), original);
});
