import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { act, create } from 'react-test-renderer';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { createServer } from 'vite';

test('collapsible history reuses persisted cases without saving drafts or rerunning analysis', async (t) => {
  const server = await createServer({ configFile: false, appType: 'custom', server: { middlewareMode: true, hmr: false, ws: false, watch: null } });
  const previous = { storage: globalThis.localStorage, window: globalThis.window, fetch: globalThis.fetch, act: globalThis.IS_REACT_ACT_ENVIRONMENT };
  const storage = new Map();
  const events = new EventTarget();
  let wide = true, duplicate = false, failList = false;
  const media = new EventTarget();
  Object.defineProperty(media, 'matches', { get: () => wide });
  globalThis.localStorage = { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, String(value)), removeItem: (key) => storage.delete(key) };
  globalThis.window = { location: { hash: '#/case' }, matchMedia: () => media,
    addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events), dispatchEvent: events.dispatchEvent.bind(events) };
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const records = ['23', '22', '21'].map((number) => ({ id: `uuid-${number}`, protocol_no: `VAKA${number}`, sex: 'male', metadata_json: {}, created_at: '2026-10-01', updated_at: '2026-10-02' }));
  const requests = [];
  const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
  let renderer, savedCase;
  globalThis.fetch = async (url, options = {}) => {
    const path = String(url); requests.push({ path, ...options });
    if (path.includes('/patients?')) {
      if (failList) return json({ detail: 'Geçici bağlantı hatası' }, 503);
      return json(records);
    }
    if (options.method === 'PATCH') {
      if (duplicate) return json({ detail: 'Bu isimde başka bir vaka zaten mevcut.' }, 409);
      const record = records.find((item) => path.includes(item.id));
      const name = JSON.parse(options.body).case_name;
      record.case_name = name; record.metadata_json = { ...record.metadata_json, case_name: name };
      if (savedCase?.patient_id === record.id) savedCase.case_name = name;
      return json(record);
    }
    if (path.includes('/simple-case/patients/uuid-23')) return json(savedCase);
    throw new Error(`Unexpected sidebar request: ${path}`);
  };
  const text = (node) => typeof node === 'string' ? node : (Array.isArray(node) ? node : node?.children ?? []).map(text).join('');
  const button = (label) => renderer.root.findAllByType('button').find((node) => text(node) === label);
  const toggle = () => renderer.root.findAllByType('button').find((node) => node.props['aria-controls']);
  const search = () => renderer.root.findByProps({ type: 'search' });
  try {
    const Panel = (await server.ssrLoadModule('/src/components/patient/CaseHistorySidebar.tsx')).default;
    const Workspace = (await server.ssrLoadModule('/src/pages/SimpleCaseWorkspacePage.tsx')).default;
    const patients = await server.ssrLoadModule('/src/services/patientClient.ts');
    const scope = await server.ssrLoadModule('/src/services/patientScope.ts');
    const { normalizeClinical } = await server.ssrLoadModule('/src/services/clinicalRecord.ts');
    const clinical = normalizeClinical({ age: 38, sex: 'male', complaints: ['Saved complaint'], notes: 'Existing clinical note' });
    savedCase = { patient_id: 'uuid-23', protocol_no: 'VAKA23', sex: 'male', age: 38, clinical,
      simple_case: { contract_version: 'medicore-simple-case-v1', clinical, labs: [], reports: [], warnings: [] },
      ai_report: { report_text: 'KLİNİK ÖZET\nSaved AI content.\n\nHEKİM NOTU\nExact existing report.', model: 'test-saved-only' } };
    patients.activatePatientRecord({ ...records[0], clinical });
    storage.set('medicore:lastLabReportId', 'saved-lab'); storage.set('medicore:lastCombinedReview', 'saved-AI');
    await act(async () => { renderer = create(React.createElement(MemoryRouter, { initialEntries: ['/case?patient=uuid-23&step=summary'] },
      React.createElement(Panel), React.createElement(Routes, null, React.createElement(Route, { path: '/case', element: React.createElement(Workspace) })))); });

    await t.test('collapsed panel never loads a list; expansion fetches read-only data and uses independent scrolling', async () => {
      assert.equal(toggle().props['aria-expanded'], false);
      assert.equal(requests.filter((request) => request.path.includes('/patients?')).length, 0);
      // An unsaved browser draft must not be submitted merely to open navigation.
      const draft = JSON.parse(storage.get(patients.ACTIVE_CLINICAL_INTAKE_KEY));
      draft.physical_exam.examination_findings = 'Unsaved draft note';
      storage.set(patients.ACTIVE_CLINICAL_INTAKE_KEY, JSON.stringify(draft));
      await act(async () => toggle().props.onClick());
      assert.equal(toggle().props['aria-expanded'], true);
      assert.equal(search().props.placeholder, 'Vaka adı ara...');
      assert.ok(renderer.root.findByProps({ 'aria-label': 'Kayıtlı vaka listesi' }).props.className.includes('overflow-y-auto'));
      assert.ok(!requests.some((request) => ['POST', 'PUT', 'DELETE'].includes(request.method)));
      assert.ok(text(renderer.toJSON()).includes('Saved AI content.'));
    });

    await t.test('sidebar search is case insensitive and supports partial names', async () => {
      for (const query of ['vaka22', '22']) {
        await act(async () => search().props.onChange({ target: { value: query } }));
        assert.ok(button('VAKA22')); assert.equal(button('VAKA23'), undefined);
      }
      await act(async () => search().props.onChange({ target: { value: '' } }));
    });

    await t.test('context actions are only Open/Rename and duplicate errors preserve the old record', async () => {
      await act(async () => renderer.root.findByProps({ 'aria-label': 'VAKA23 işlemleri' }).props.onClick());
      assert.ok(button('Aç')); assert.ok(button('Adını Değiştir'));
      assert.equal(button('Sil'), undefined); assert.equal(button('Detayları göster'), undefined);
      await act(async () => button('Adını Değiştir').props.onClick({ currentTarget: { closest: () => null } }));
      await act(async () => renderer.root.findByProps({ type: 'text' }).props.onChange({ target: { value: 'VAKA22' } }));
      duplicate = true;
      await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
      assert.equal(text(renderer.root.findByProps({ role: 'alert' })), 'Bu isimde başka bir vaka zaten mevcut.');
      assert.equal(records[0].case_name, undefined);
    });

    await t.test('rename updates sidebar and active case heading without reloading clinical or AI data', async () => {
      duplicate = false;
      const caseReads = requests.filter((request) => request.path.includes('/simple-case/')).length;
      const snapshot = new Map(storage), generation = scope.patientScopeVersion();
      await act(async () => renderer.root.findByProps({ type: 'text' }).props.onChange({ target: { value: 'VAKA24' } }));
      await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
      assert.ok(button('VAKA24'));
      assert.equal(text(renderer.root.findByType('h1')), 'VAKA24');
      assert.equal(requests.filter((request) => request.path.includes('/simple-case/')).length, caseReads);
      assert.equal(scope.patientScopeVersion(), generation);
      for (const key of [patients.ACTIVE_CLINICAL_INTAKE_KEY, 'medicore:lastCombinedReview', 'medicore:lastLabReportId']) assert.equal(storage.get(key), snapshot.get(key));
      assert.deepEqual(JSON.parse(requests.filter((request) => request.method === 'PATCH').at(-1).body), { case_name: 'VAKA24' });
      assert.equal(records[0].id, 'uuid-23'); assert.equal(records[0].protocol_no, 'VAKA23');
      assert.ok(text(renderer.toJSON()).includes('Exact existing report.'));
    });

    await t.test('collapse hides all case rows, and reopen restores persisted renamed data', async () => {
      await act(async () => toggle().props.onClick());
      assert.equal(renderer.root.findAllByProps({ type: 'search' }).length, 0);
      assert.equal(button('VAKA24'), undefined);
      await act(async () => toggle().props.onClick());
      assert.ok(button('VAKA24'));
    });

    await t.test('opening an existing case reuses the UUID and does not create or analyse a replacement', async () => {
      await act(async () => button('VAKA24').props.onClick());
      assert.equal(patients.getActivePatientId(), 'uuid-23');
      assert.equal(text(renderer.root.findByType('h1')), 'VAKA24');
      assert.ok(!requests.some((request) => /ai-interpretation/.test(request.path)));
      assert.ok(!requests.some((request) => ['POST', 'PUT', 'DELETE'].includes(request.method)));
    });

    await t.test('read errors are retryable and never write clinical data', async () => {
      await act(async () => toggle().props.onClick());
      failList = true;
      await act(async () => toggle().props.onClick());
      assert.ok(text(renderer.root.findByProps({ role: 'alert' })).includes('Geçici bağlantı hatası'));
      failList = false;
      await act(async () => button('Yeniden dene').props.onClick());
      assert.equal(renderer.root.findAllByProps({ role: 'alert' }).length, 0);
    });

    await t.test('mobile history opens as a dialog, closes on cancel and hides after case selection', async () => {
      await act(async () => renderer.unmount());
      wide = false;
      await act(async () => { renderer = create(React.createElement(MemoryRouter, { initialEntries: ['/case'] }, React.createElement(Panel, { mobile: true }))); });
      await act(async () => toggle().props.onClick());
      assert.equal(renderer.root.findAllByType('dialog').length, 1);
      await act(async () => renderer.root.findByType('dialog').props.onCancel());
      assert.equal(renderer.root.findAllByType('dialog').length, 0);
      await act(async () => toggle().props.onClick());
      await act(async () => button('VAKA24').props.onClick());
      assert.equal(renderer.root.findAllByType('dialog').length, 0);
      assert.equal(patients.getActivePatientId(), 'uuid-23');
    });
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.localStorage = previous.storage; globalThis.window = previous.window; globalThis.fetch = previous.fetch; globalThis.IS_REACT_ACT_ENVIRONMENT = previous.act;
    await server.close();
  }
});
