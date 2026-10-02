import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { normalizeClinical, vitalDraft } from '../src/services/clinicalRecord.ts';

// Vite applies the application's TSX/env transforms. Components render as HTML,
// and storage/fetch are isolated doubles; this test never contacts a backend.
test('clinical cards, numeric inputs and archive draft synchronization', async (t) => {
  const server = await createServer({ configFile: false, appType: 'custom', server: { middlewareMode: true, hmr: false, watch: null } });
  const originalStorage = globalThis.localStorage;
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  try {
    const Summary = (await server.ssrLoadModule('/src/components/clinical/ClinicalHistorySummary.tsx')).default;
    const Fields = (await server.ssrLoadModule('/src/components/clinical/VitalSignsFields.tsx')).default;
    const patientClient = await server.ssrLoadModule('/src/services/patientClient.ts');
    const legacyForm = await server.ssrLoadModule('/src/components/clinical/ClinicalIntakeForm.tsx');
    const clinical = normalizeClinical({ complaints: ['kusma', 'kuruluk'], history: ['Hipertansiyon'], medications: ['amlodipin'], notes: 'Muayene notu', vital_signs: { heart_rate: 108, spo2: 97, height_cm: 178, weight_kg: 82, glucose_mg_dl: 108 } });

    await t.test('all history sections render without the empty message', () => {
      const html = renderToStaticMarkup(React.createElement(Summary, { clinical }));
      for (const text of ['Şikayetler', 'Özgeçmiş / Hastalıklar', 'İlaçlar', 'Ek Klinik Not', 'Vital Bulgular', 'Nabız 108/dk', 'SpO₂ %97']) assert.ok(html.includes(text), text);
      assert.ok(!html.includes('Henüz klinik bilgi eklenmedi'));
      assert.ok(html.includes('kusma\nkuruluk'));
    });
    await t.test('notes-only and vitals-only cases are not classified as empty', () => {
      for (const source of [{ notes: 'Sadece not' }, { vital_signs: { heart_rate: 0 } }]) {
        const html = renderToStaticMarkup(React.createElement(Summary, { clinical: normalizeClinical(source) }));
        assert.ok(!html.includes('Henüz klinik bilgi eklenmedi'));
      }
      const empty = renderToStaticMarkup(React.createElement(Summary, { clinical: normalizeClinical({}) }));
      assert.ok(empty.includes('Henüz klinik bilgi eklenmedi'));
    });
    await t.test('all nine optional measurements render as numeric inputs with units', () => {
      const html = renderToStaticMarkup(React.createElement(Fields, { values: vitalDraft(clinical.vital_signs), onChange() {} }));
      assert.equal((html.match(/type="number"/g) ?? []).length, 9);
      for (const unit of ['mmHg', 'bpm', '/dk', '°C', '%', 'cm', 'kg', 'mg/dL']) assert.ok(html.includes(unit));
      assert.ok(html.includes('value="108"'));
    });
    await t.test('opening the archive does not rewrite an unchanged saved case', async () => {
      const storage = new Map();
      globalThis.localStorage = { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) };
      globalThis.window = { location: { hash: '#/patients' } };
      let writes = 0;
      globalThis.fetch = async () => { writes++; throw new Error('test fetch'); };
      patientClient.setActiveClinicalDraft('patient-1', 'VAKA01', clinical);
      const draft = JSON.parse(storage.get(patientClient.ACTIVE_CLINICAL_INTAKE_KEY));
      assert.equal(draft.physical_exam.pulse_bpm, 108);
      assert.equal(draft.patient_information.height_cm, 178);
      assert.equal(legacyForm.readStoredClinicalIntake().vital_signs.glucose_mg_dl, 108);
      assert.equal(await patientClient.syncActivePatientDraft(), null);
      assert.equal(writes, 0);
      draft.physical_exam.pulse_bpm = 92;
      storage.set(patientClient.ACTIVE_CLINICAL_INTAKE_KEY, JSON.stringify(draft));
      await patientClient.syncActivePatientDraft();
      assert.equal(writes, 1);
    });
  } finally {
    globalThis.localStorage = originalStorage;
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
    await server.close();
  }
});
