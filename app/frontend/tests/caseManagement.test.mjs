import assert from 'node:assert/strict';
import test from 'node:test';
import { caseDisplayName, caseNameMatches, normalizeCaseName } from '../src/services/caseManagement.ts';

test('legacy protocols remain display names without a backfill or identifier change', () => {
  const record = { id: 'uuid-A', protocol_no: 'VAKA23', metadata_json: {} };
  assert.equal(caseDisplayName(record), 'VAKA23');
  const renamed = { ...record, metadata_json: { case_name: 'VAKA22' } };
  assert.equal(caseDisplayName(renamed), 'VAKA22');
  assert.equal(renamed.id, record.id);
  assert.equal(renamed.protocol_no, record.protocol_no);
  assert.equal(caseDisplayName({ ...renamed, case_name: 'Current label' }), 'Current label');
});

test('name search supports case-insensitive and partial matches on existing data', () => {
  const record = { protocol_no: 'VAKA23', case_name: 'VAKA22', metadata_json: {} };
  for (const query of ['VAKA22', 'vaka22', '22', ' VAK ']) assert.equal(caseNameMatches(record, query), true);
  assert.equal(caseNameMatches(record, '23'), false);
  assert.equal(caseNameMatches({ ...record, case_name: 'VAKAI' }, 'vakai'), true);
  assert.equal(normalizeCaseName('  ＶＡＫＡ22  '), 'vaka22');
});
