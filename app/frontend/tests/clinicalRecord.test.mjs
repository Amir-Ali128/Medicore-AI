import assert from 'node:assert/strict';
import test from 'node:test';
import { clinicalRows, formatVitals, legacyClinicalIntake, normalizeClinical, parseVitalDraft, recordClinical, vitalDraft } from '../src/services/clinicalRecord.ts';
import { simpleCaseInputKey } from '../src/services/simpleCaseInputKey.ts';

function clinicalData() {
  return {
    age: 38, sex: 'male', complaints: ['2 gündür kusma', 'ağız kuruluğu', 'halsizlik', 'idrar miktarında azalma'],
    history: ['Hipertansiyon', '5 yıl önce böbrek taşı', 'baba kolon kanseri', 'penisilin alerjisi'],
    medications: ['amlodipin 5 mg/gün'], notes: 'Ağız mukozası kuru, cilt turgoru azalmış, hafif taşikardik…',
    vital_signs: parseVitalDraft({ ...vitalDraft(), systolic_bp: '145', diastolic_bp: '90', heart_rate: '108', temperature: '37.2', spo2: '97', height_cm: '178', weight_kg: '82', glucose_mg_dl: '108' }).values,
  };
}

test('flat saved clinical data displays all four sections and full multiline notes', () => {
  const source = clinicalData();
  source.notes += '\n' + 'Uzun klinik not '.repeat(30);
  const rows = clinicalRows(recordClinical({ metadata_json: { clinical_context: source } }));
  assert.deepEqual(rows.map(([label]) => label), ['Şikayetler', 'Özgeçmiş / Hastalıklar', 'İlaçlar', 'Ek Klinik Not']);
  assert.equal(rows[0][1], source.complaints.join('\n'));
  assert.equal(rows[3][1], source.notes.trim());
});

test('legacy nested history and root height/weight remain readable', () => {
  const clinical = recordClinical({ sex: 'male', metadata_json: {
    age: 38, height_cm: 178, weight_kg: 82,
    clinical_context: {
      presenting_complaint: { chief_complaint: 'kusma\nağız kuruluğu' },
      clinical_history_details: { past_medical_history: 'Hipertansiyon', family_history: 'baba kolon kanseri', medications: 'amlodipin' },
      physical_exam: { pulse_bpm: 108, temperature_c: 37.2, examination_findings: 'Mukozalar kuru' },
    },
  } });
  assert.deepEqual(clinical.complaints, ['kusma', 'ağız kuruluğu']);
  assert.deepEqual(clinical.history, ['Hipertansiyon', 'baba kolon kanseri']);
  assert.equal(clinical.vital_signs.height_cm, 178);
  assert.equal(clinical.vital_signs.heart_rate, 108);
  assert.equal(clinical.sex, 'male');
});

test('canonical snapshot and additive detail fields take precedence over stale metadata', () => {
  const clinical = clinicalData();
  const metadata = { height_cm: 199, weight_kg: 99, clinical_context: { notes: 'eski' }, simple_case: { clinical } };
  const resolved = recordClinical({ metadata_json: metadata });
  assert.equal(resolved.vital_signs.height_cm, 178);
  assert.equal(resolved.notes, clinical.notes);
  assert.equal(recordClinical({ clinical: { ...clinical, notes: 'en güncel' }, metadata_json: metadata }).notes, 'en güncel');
});

test('cleared measurements remain absent even when legacy height/weight exist', () => {
  const clinical = normalizeClinical({ vital_signs: null, notes: 'not' }, { height_cm: 199, weight_kg: 99 });
  assert.deepEqual(formatVitals(clinical.vital_signs), []);
  assert.equal(clinical.vital_signs.height_cm, null);
  assert.equal(clinicalRows(clinical)[0][1], 'not');
});

test('numeric form converts decimals, retains zero and rejects malformed or out-of-range values', () => {
  const parsed = parseVitalDraft({ ...vitalDraft(), temperature: '37,2', heart_rate: '0', spo2: '97' });
  assert.deepEqual(parsed.errors, []);
  assert.equal(parsed.values.temperature, 37.2);
  assert.equal(parsed.values.heart_rate, 0);
  assert.equal(parsed.values.weight_kg, null);
  for (const edit of [{ spo2: '101' }, { heart_rate: 'NaN' }, { weight_kg: '-1' }, { temperature: 'Infinity' }]) {
    assert.ok(parseVitalDraft({ ...vitalDraft(), ...edit }).errors.length > 0);
  }
  assert.equal(normalizeClinical({ vital_signs: { heart_rate: true, spo2: 101 } }).vital_signs.heart_rate, null);
});

test('compact vital display omits missing parameters and never invents half a blood pressure', () => {
  const clinical = clinicalData();
  assert.equal(formatVitals(clinical.vital_signs).slice(0, 4).join(' · '), 'TA 145/90 mmHg · Nabız 108/dk · Ateş 37.2°C · SpO₂ %97');
  assert.deepEqual(formatVitals({ heart_rate: 0, systolic_bp: 145 }), ['Sistolik TA 145 mmHg', 'Nabız 0/dk']);
  assert.deepEqual(formatVitals(null), []);
});

test('legacy form adapter round-trips structured history, vital signs and optional glucose', () => {
  const clinical = clinicalData();
  const adapted = legacyClinicalIntake(clinical);
  assert.deepEqual(normalizeClinical(adapted), clinical);
  assert.equal(adapted.patient_information.height_cm, clinical.vital_signs.height_cm);
  assert.equal(adapted.physical_exam.pulse_bpm, 108);
  assert.equal(adapted.vital_signs.glucose_mg_dl, 108);
});

test('legacy adapter preserves separate associated symptoms without duplicating history', () => {
  const previous = {
    patient_information: { full_name: 'Test', age: 38, sex: 'male' },
    presenting_complaint: { chief_complaint: 'kusma', associated_symptoms: 'kuruluk', complaint_duration: '2 gün' },
    clinical_history_details: { past_medical_history: 'HT', family_history: 'kanser' },
    imaging_results: { ultrasound: 'eski rapor' },
  };
  const clinical = normalizeClinical(previous);
  const adapted = legacyClinicalIntake(clinical, previous);
  assert.deepEqual(normalizeClinical(adapted), clinical);
  assert.equal(adapted.imaging_results.ultrasound, 'eski rapor');
});

test('editing a structured vital invalidates an earlier AI report key', () => {
  const payload = { clinical: clinicalData(), labs: [], reports: [] };
  const before = simpleCaseInputKey('case-1', payload);
  payload.clinical.vital_signs.heart_rate = 92;
  assert.notEqual(simpleCaseInputKey('case-1', payload), before);
});

test('a stale legacy draft cannot overwrite newer canonical complaints or history', () => {
  const clinical = clinicalData();
  const previous = {
    patient_information: { full_name: 'Test' },
    presenting_complaint: { chief_complaint: 'eski şikayet', associated_symptoms: 'eski belirti' },
    clinical_history_details: { past_medical_history: 'eski öykü', family_history: 'eski aile öyküsü' },
    imaging_results: { ultrasound: 'korunacak rapor' },
  };
  const adapted = legacyClinicalIntake(clinical, previous);
  assert.deepEqual(normalizeClinical(adapted), clinical);
  assert.equal(adapted.imaging_results.ultrasound, 'korunacak rapor');
});

test('clinical and vital event dates survive the legacy adapter independently', () => {
  const clinical = { ...clinicalData(), event_date: '2026-10-02', vitals_event_date: '2026-10-02T16:00:00+03:00' };
  const restored = normalizeClinical(legacyClinicalIntake(clinical));
  assert.deepEqual(restored, clinical);
  assert.ok(!('event_date' in restored.vital_signs));
  assert.equal(restored.vitals_event_date, clinical.vitals_event_date);
  const payload = { clinical, labs: [], reports: [] };
  const original = simpleCaseInputKey('case-1', payload);
  payload.clinical.event_date = '2026-10-03';
  assert.notEqual(simpleCaseInputKey('case-1', payload), original);
});

test('legacy explicit measurement dates are preserved without inventing dates', () => {
  const restored = normalizeClinical({ examination_date: '2026-10-02', physical_exam: { measurement_date: '2026-10-03', pulse_bpm: 108 } });
  assert.equal(restored.event_date, '2026-10-02');
  assert.equal(restored.vitals_event_date, '2026-10-03');
  assert.equal(restored.vital_signs.heart_rate, 108);
  assert.ok(!('event_date' in normalizeClinical({ notes: 'Tarihsiz not' })));
});

test('explicitly cleared event dates cannot reappear from old legacy aliases', () => {
  const previous = { examination_date: '2026-10-01', physical_exam: {
    examination_date: '2026-10-01', measurement_date: '2026-10-01', pulse_bpm: 108 } };
  const cleared = normalizeClinical({ ...previous, event_date: null, vitals_event_date: null });
  assert.equal(cleared.event_date, null);
  assert.equal(cleared.vitals_event_date, null);
  const adapted = legacyClinicalIntake(cleared, previous);
  assert.equal(adapted.event_date, null);
  assert.equal(adapted.vitals_event_date, null);
  assert.equal(adapted.physical_exam.examination_date, null);
  assert.equal(adapted.physical_exam.measurement_date, null);
  assert.deepEqual(normalizeClinical(adapted), cleared);
});
