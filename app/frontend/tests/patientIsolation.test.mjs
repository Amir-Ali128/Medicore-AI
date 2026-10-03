import assert from 'node:assert/strict';
import test from 'node:test';
import { createServer } from 'vite';

test('patient switches isolate drafts, reports, late responses and AI context', async (t) => {
  const server = await createServer({ configFile: false, appType: 'custom', server: { middlewareMode: true, hmr: false, watch: null } });
  const originals = { storage: globalThis.localStorage, window: globalThis.window, fetch: globalThis.fetch };
  const storage = new Map();
  const events = [];
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key),
  };
  globalThis.window = { location: { hash: '#/case' }, dispatchEvent: (event) => { events.push(event.type); return true; } };
  try {
    const patients = await server.ssrLoadModule('/src/services/patientClient.ts');
    const scopes = await server.ssrLoadModule('/src/services/patientScope.ts');
    const brain = await server.ssrLoadModule('/src/services/clinicalBrainClient.ts');
    const lab = await server.ssrLoadModule('/src/services/labAnalysisClient.ts');
    const archive = await server.ssrLoadModule('/src/services/labArchiveClient.ts');
    const radiology = await server.ssrLoadModule('/src/services/radiologyClient.ts');
    const form = await server.ssrLoadModule('/src/components/clinical/ClinicalIntakeForm.tsx');
    const { normalizeClinical } = await server.ssrLoadModule('/src/services/clinicalRecord.ts');
    const record = (id, complaint, age = 30) => ({
      id, protocol_no: `VAKA-${id}`, sex: 'male', date_of_birth: null,
      metadata_json: { clinical_context: { complaints: [complaint], history: [], medications: [], notes: null, age, sex: 'male', vital_signs: { heart_rate: id === 'A' ? 108 : 72 } } },
    });
    const a = record('A', 'Hasta A şikayeti');
    const b = record('B', 'Hasta B şikayeti', 65);
    const json = (value) => new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } });
    const deferred = () => {
      let resolve;
      const promise = new Promise((done) => { resolve = done; });
      return { promise, resolve };
    };
    const reset = () => { scopes.clearPatientScope(); storage.clear(); events.length = 0; };

    await t.test('A → B clears every active pointer and restores only A on return', () => {
      reset();
      patients.activatePatientRecord(a);
      storage.set('medicore:lastAnalysisRunId', 'analysis-A');
      storage.set('medicore:lastLabReportId', 'lab-A');
      storage.set('medicore:lastRadiologyReportId', 'report-A');
      storage.set('medicore:lastCombinedReview', 'AI-A');
      const previous = scopes.capturePatientScope();
      patients.activatePatientRecord(b);
      assert.equal(previous.signal.aborted, true);
      assert.equal(scopes.isCurrentPatientScope(previous), false);
      for (const key of ['medicore:lastAnalysisRunId', 'medicore:lastLabReportId', 'medicore:lastRadiologyReportId', 'medicore:lastCombinedReview']) assert.equal(storage.get(key), undefined);
      assert.equal(form.readStoredClinicalIntake().physical_exam.pulse_bpm, 72);
      assert.equal(form.readStoredClinicalIntake().presenting_complaint.chief_complaint, 'Hasta B şikayeti');
      assert.equal(storage.get('medicore:lastPatientAge'), '65');
      storage.set('medicore:lastLabReportId', 'lab-B');
      patients.activatePatientRecord(a);
      assert.equal(storage.get('medicore:lastLabReportId'), 'lab-A');
      assert.equal(storage.get('medicore:lastCombinedReview'), 'AI-A');
      assert.equal(form.readStoredClinicalIntake().physical_exam.pulse_bpm, 108);
      assert.ok(events.includes(scopes.PATIENT_SCOPE_CHANGED_EVENT));
    });

    await t.test('switching back to A does not make an old A request current', () => {
      reset(); patients.activatePatientRecord(a);
      const old = scopes.capturePatientScope();
      patients.activatePatientRecord(b); patients.activatePatientRecord(a);
      assert.equal(scopes.isCurrentPatientScope(old), false);
      assert.throws(() => scopes.assertCurrentPatientScope(old), { name: 'AbortError' });
    });

    await t.test('same-patient saving preserves scope and reports', () => {
      reset(); patients.activatePatientRecord(a);
      storage.set('medicore:lastLabReportId', 'lab-A');
      const previous = scopes.capturePatientScope();
      patients.setActiveClinicalDraft('A', a.protocol_no, normalizeClinical(a.metadata_json.clinical_context));
      assert.equal(scopes.isCurrentPatientScope(previous), true);
      assert.equal(storage.get('medicore:lastLabReportId'), 'lab-A');
    });

    await t.test('reading A while B is active does not select A', async () => {
      reset(); patients.activatePatientRecord(b);
      globalThis.fetch = async () => json(a);
      assert.equal((await patients.getPatientRecord('A')).id, 'A');
      assert.equal(patients.getActivePatientId(), 'B');
      assert.equal(form.readStoredClinicalIntake().presenting_complaint.chief_complaint, 'Hasta B şikayeti');
    });

    await t.test('a late background save cannot replace B with A', async () => {
      reset(); patients.activatePatientRecord(a);
      const draft = form.readStoredClinicalIntake(); draft.presenting_complaint.chief_complaint = 'A düzenlemesi';
      storage.set(patients.ACTIVE_CLINICAL_INTAKE_KEY, JSON.stringify(draft));
      const pending = deferred(); let signal;
      globalThis.fetch = async (_url, init) => { signal = init.signal; return pending.promise; };
      const saving = patients.syncActivePatientDraft();
      patients.activatePatientRecord(b);
      assert.equal(signal.aborted, true);
      pending.resolve(json(a));
      assert.equal(await saving, null);
      assert.equal(patients.getActivePatientId(), 'B');
      assert.equal(form.readStoredClinicalIntake().presenting_complaint.chief_complaint, 'Hasta B şikayeti');
    });

    await t.test('a late explicit save is rejected even if transport ignores abort', async () => {
      reset(); patients.activatePatientRecord(a);
      const pending = deferred();
      globalThis.fetch = async () => pending.promise;
      const saving = patients.savePatientRecord(form.readStoredClinicalIntake());
      patients.activatePatientRecord(b); pending.resolve(json(a));
      await assert.rejects(saving, { name: 'AbortError' });
      assert.equal(patients.getActivePatientId(), 'B');
    });

    await t.test('background response cannot discard newer edits to the same patient', async () => {
      reset(); patients.activatePatientRecord(a);
      const draft = form.readStoredClinicalIntake(); draft.presenting_complaint.chief_complaint = 'İlk düzenleme';
      storage.set(patients.ACTIVE_CLINICAL_INTAKE_KEY, JSON.stringify(draft));
      const pending = deferred(); globalThis.fetch = async () => pending.promise;
      const saving = patients.syncActivePatientDraft();
      draft.presenting_complaint.chief_complaint = 'Daha yeni düzenleme';
      storage.set(patients.ACTIVE_CLINICAL_INTAKE_KEY, JSON.stringify(draft));
      pending.resolve(json(a)); await saving;
      assert.equal(form.readStoredClinicalIntake().presenting_complaint.chief_complaint, 'Daha yeni düzenleme');
      assert.notEqual(storage.get(patients.ACTIVE_CLINICAL_INTAKE_KEY), storage.get('medicore:syncedClinicalDraft'));
    });

    await t.test('an old form and old analysis cannot write to B storage', () => {
      reset(); patients.activatePatientRecord(a);
      const scope = scopes.capturePatientScope(); const draft = form.readStoredClinicalIntake();
      patients.activatePatientRecord(b);
      form.persistClinicalIntake(draft, scope);
      lab.rememberLatestAnalysis({ patient_id: 'A', analysis_run_id: 'analysis-A', lab_report_id: 'lab-A' }, scope);
      assert.equal(storage.get('medicore:lastLabReportId'), undefined);
      assert.equal(form.readStoredClinicalIntake().physical_exam.pulse_bpm, 72);
    });

    await t.test('AI restoration stops before submission after changing patients', async () => {
      reset(); patients.activatePatientRecord(a);
      const pending = deferred(); const requested = [];
      globalThis.fetch = async (url) => { requested.push(url); return pending.promise; };
      const evaluation = brain.evaluateClinicalBrain({ clinical_context: null, lab_results: [], radiology_reports: [] });
      patients.activatePatientRecord(b); pending.resolve(json(a));
      await assert.rejects(evaluation, { name: 'AbortError' });
      assert.equal(requested.length, 1);
      assert.ok(!requested.some((url) => url.includes('/clinical-brain/evaluate')));
      assert.equal(patients.getActivePatientId(), 'B');
    });

    await t.test('AI rejects imaging from a different active patient', async () => {
      reset(); patients.activatePatientRecord(b);
      let requests = 0; globalThis.fetch = async () => { requests++; throw new Error('unexpected'); };
      await assert.rejects(brain.evaluateClinicalBrain({ clinical_context: null, lab_results: [], radiology_reports: [{ patient_id: 'A' }] }), /eşleşmiyor/);
      assert.equal(requests, 0);
    });

    await t.test('scoped snapshots never restore another account’s data', () => {
      reset(); storage.set('medicore:clinicalCurrentUser', JSON.stringify({ id: 'user-1' }));
      patients.activatePatientRecord(a); storage.set('medicore:lastLabReportId', 'user-1-lab-A');
      patients.activatePatientRecord(b);
      storage.set('medicore:clinicalCurrentUser', JSON.stringify({ id: 'user-2' }));
      patients.activatePatientRecord(a);
      assert.equal(storage.get('medicore:lastLabReportId'), undefined);
    });

    await t.test('source binding refuses to relabel another patient’s document', () => {
      assert.deepEqual(scopes.bindPatientMetadata({ source_file_name: 'a.pdf' }, 'A'), { source_file_name: 'a.pdf', patient_id: 'A' });
      assert.throws(() => scopes.bindPatientMetadata({ patient_id: 'A' }, 'B'), /eşleşmiyor/);
    });

    await t.test('a new patient clears all active clinical, vital and result state', () => {
      reset(); patients.activatePatientRecord(a);
      storage.set('medicore:lastLabReportId', 'lab-A'); storage.set('medicore:lastCombinedReview', 'AI-A');
      const previous = scopes.capturePatientScope(); patients.clearActivePatientRecord();
      assert.equal(previous.signal.aborted, true);
      assert.equal(patients.getActivePatientId(), null);
      assert.equal(form.readStoredClinicalIntake(), null);
      for (const key of scopes.PATIENT_SESSION_KEYS) assert.equal(storage.get(key), undefined);
    });

    await t.test('old unscoped pointers are discarded when a legacy session is activated', () => {
      reset(); storage.set(patients.ACTIVE_PATIENT_ID_KEY, 'A'); storage.set('medicore:lastLabReportId', 'unverified-old-pointer');
      patients.activatePatientRecord(a);
      assert.equal(storage.get('medicore:lastLabReportId'), undefined);
      assert.equal(form.readStoredClinicalIntake().physical_exam.pulse_bpm, 108);
    });

    await t.test('late PDF cannot populate its popup after selecting B', async () => {
      reset(); patients.activatePatientRecord(a);
      const popup = { document: { title: '' }, location: { href: '' }, closeCount: 0, close() { this.closeCount++; } };
      globalThis.window.open = () => popup;
      const pending = deferred(); let signal;
      globalThis.fetch = async (_url, init) => { signal = init.signal; return pending.promise; };
      const opening = archive.openLabReportPdf('lab-A', 'A.pdf');
      patients.activatePatientRecord(b);
      assert.equal(signal.aborted, true); assert.ok(popup.closeCount >= 1);
      pending.resolve(new Response(new Blob(['pdf-A'], { type: 'application/pdf' })));
      await assert.rejects(opening, { name: 'AbortError' });
      assert.equal(popup.location.href, ''); assert.equal(popup.document.title, '');
    });

    await t.test('late archive attachment does not submit A context after selecting B', async () => {
      reset(); patients.activatePatientRecord(a);
      const draft = form.readStoredClinicalIntake(); const pending = deferred(); const requested = [];
      globalThis.fetch = async (url) => { requested.push(url); return pending.promise; };
      const attaching = archive.saveLabReportToPatient('lab-A', 'A', draft);
      patients.activatePatientRecord(b); pending.resolve(json({ id: 'lab-A', patient_id: 'A' }));
      await assert.rejects(attaching, { name: 'AbortError' });
      assert.equal(requested.length, 1); assert.ok(!requested.some((url) => url.includes('clinical-context')));
    });

    await t.test('late radiology upload does not replace B’s report pointer', async () => {
      reset(); patients.activatePatientRecord(a);
      const pending = deferred(); globalThis.fetch = async () => pending.promise;
      const uploading = radiology.createManualRadiologyReport({ reportDate: null, modality: null, bodyPart: null, reportText: 'A tetkik' });
      patients.activatePatientRecord(b); storage.set('medicore:lastRadiologyReportId', 'report-B');
      pending.resolve(json({ id: 'report-A', patient_id: 'A', metadata_json: {} }));
      await assert.rejects(uploading, { name: 'AbortError' });
      assert.equal(storage.get('medicore:lastRadiologyReportId'), 'report-B');
    });

    await t.test('late radiology file download and delete reject after selecting B', async () => {
      for (const operation of ['download', 'delete']) {
        reset(); patients.activatePatientRecord(a);
        const pending = deferred(); globalThis.fetch = async () => pending.promise;
        const request = operation === 'download' ? radiology.downloadRadiologyOriginalFile('report-A') : radiology.deleteRadiologyReport('report-A');
        patients.activatePatientRecord(b); storage.set('medicore:lastRadiologyReportId', 'report-B');
        pending.resolve(operation === 'download' ? new Response(new Blob(['pdf-A'])) : new Response(null, { status: 204 }));
        await assert.rejects(request, { name: 'AbortError' });
        assert.equal(storage.get('medicore:lastRadiologyReportId'), 'report-B');
      }
    });
  } finally {
    globalThis.localStorage = originals.storage; globalThis.window = originals.window; globalThis.fetch = originals.fetch;
    await server.close();
  }
});
