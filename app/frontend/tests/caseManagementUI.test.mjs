import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { act, create } from 'react-test-renderer';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { createServer } from 'vite';

test('history searches, renames and opens persisted cases without changing UUIDs or clinical state', async (t) => {
  const server = await createServer({ configFile: false, appType: 'custom', server: { middlewareMode: true, hmr: false, ws: false, watch: null } });
  const previous = { storage: globalThis.localStorage, window: globalThis.window, fetch: globalThis.fetch, act: globalThis.IS_REACT_ACT_ENVIRONMENT };
  const storage = new Map();
  globalThis.localStorage = { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, String(value)), removeItem: (key) => storage.delete(key) };
  globalThis.window = { location: { hash: '#/history' }, dispatchEvent: () => true, addEventListener() {}, removeEventListener() {} };
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const records = ['23', '21'].map((number) => ({ id: `uuid-${number}`, protocol_no: `VAKA${number}`, sex: 'male', external_ref: null, date_of_birth: null, is_pregnant: null,
    metadata_json: { clinical_context: { complaints: ['Existing complaint'], notes: 'Original notes' } }, created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-02T10:00:00Z' }));
  const requests = [];
  let rejectDuplicate = false;
  const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url: String(url), ...options });
    if (options.method === 'PATCH') {
      if (rejectDuplicate) return json({ detail: 'Bu isimde başka bir vaka zaten mevcut.' }, 409);
      const name = JSON.parse(options.body).case_name;
      const record = records.find((item) => String(url).includes(item.id));
      record.case_name = name; record.metadata_json = { ...record.metadata_json, case_name: name };
      return json(record);
    }
    if (String(url).includes('/patients?')) return json(records);
    if (String(url).endsWith('/patients/uuid-23')) return json(records[0]);
    return json([]);
  };
  let renderer;
  const text = (node) => typeof node === 'string' ? node : (node?.children ?? []).map(text).join('');
  const button = (label) => renderer.root.findAllByType('button').find((node) => text(node) === label);
  function SelectedCase() { const location = useLocation(); return React.createElement('p', { 'data-route': location.pathname + location.search }, 'Selected case'); }
  try {
    const Page = (await server.ssrLoadModule('/src/pages/PatientHistoryPage.tsx')).default;
    const Resume = (await server.ssrLoadModule('/src/components/patient/LastCaseResume.tsx')).default;
    const patients = await server.ssrLoadModule('/src/services/patientClient.ts');
    const scopes = await server.ssrLoadModule('/src/services/patientScope.ts');
    patients.activatePatientRecord(records[0]);
    storage.set('medicore:lastLabReportId', 'existing-lab'); storage.set('medicore:lastCombinedReview', 'existing-AI');
    const scopeBefore = scopes.capturePatientScope();
    const draftBefore = storage.get(patients.ACTIVE_CLINICAL_INTAKE_KEY);
    await act(async () => { renderer = create(React.createElement(MemoryRouter, { initialEntries: ['/history'] }, React.createElement(Routes, null,
      React.createElement(Route, { path: '/history', element: React.createElement(Page) }), React.createElement(Route, { path: '/case', element: React.createElement(SelectedCase) })))); });

    await t.test('history starts as compact rows and name/partial search finds existing cases', async () => {
      assert.ok(text(renderer.toJSON()).includes('Geçmiş Vakalar'));
      assert.ok(!text(renderer.toJSON()).includes('Klinik Öykü'));
      const search = renderer.root.findByProps({ type: 'search' });
      assert.equal(search.props.placeholder, 'Vaka adı ara...');
      await act(async () => search.props.onChange({ target: { value: 'vaka23' } }));
      assert.ok(text(renderer.toJSON()).includes('VAKA23'));
      assert.ok(!text(renderer.toJSON()).includes('VAKA21'));
      await act(async () => search.props.onChange({ target: { value: '21' } }));
      assert.ok(text(renderer.toJSON()).includes('VAKA21'));
      assert.ok(!text(renderer.toJSON()).includes('VAKA23'));
      await act(async () => search.props.onChange({ target: { value: '' } }));
    });

    await t.test('duplicate errors keep the old case name and the editor available', async () => {
      await act(async () => button('Adını Değiştir').props.onClick({ currentTarget: { closest: () => null } }));
      await act(async () => renderer.root.findByProps({ type: 'text' }).props.onChange({ target: { value: 'VAKA21' } }));
      rejectDuplicate = true;
      await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
      assert.equal(text(renderer.root.findByProps({ role: 'alert' })), 'Bu isimde başka bir vaka zaten mevcut.');
      assert.equal(records[0].case_name, undefined);
      assert.equal(button('Adı kaydet').props.disabled, false);
    });

    await t.test('VAKA23 → VAKA22 uses a PATCH with only a display name, preserving the active draft and AI/lab pointers', async () => {
      rejectDuplicate = false;
      await act(async () => renderer.root.findByProps({ type: 'text' }).props.onChange({ target: { value: ' VAKA22 ' } }));
      await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }));
      const write = requests.filter((request) => request.method === 'PATCH').at(-1);
      assert.ok(write.url.endsWith('/patients/uuid-23/case-name'));
      assert.deepEqual(JSON.parse(write.body), { case_name: 'VAKA22' });
      assert.equal(records[0].id, 'uuid-23'); assert.equal(records[0].protocol_no, 'VAKA23');
      assert.equal(storage.get(patients.ACTIVE_CLINICAL_INTAKE_KEY), draftBefore);
      assert.equal(storage.get('medicore:lastCombinedReview'), 'existing-AI');
      assert.equal(storage.get('medicore:lastLabReportId'), 'existing-lab');
      assert.equal(scopes.isCurrentPatientScope(scopeBefore), true);
      assert.ok(text(renderer.toJSON()).includes('VAKA22'));
      await act(async () => renderer.root.findByProps({ type: 'search' }).props.onChange({ target: { value: '22' } }));
      assert.ok(!text(renderer.toJSON()).includes('VAKA21'));
    });

    await t.test('opening history reuses the selected UUID and never creates a replacement or runs AI', async () => {
      await act(async () => button('Aç').props.onClick());
      assert.equal(renderer.root.findByProps({ 'data-route': '/case?patient=uuid-23&step=summary' }).children[0], 'Selected case');
      assert.equal(patients.getActivePatientId(), 'uuid-23');
      assert.ok(!requests.some((request) => ['POST', 'PUT', 'DELETE'].includes(request.method)));
      assert.ok(!requests.some((request) => /ai-interpretation/.test(request.url)));
    });

    await t.test('resume verifies the existing persisted active pointer and offers the renamed case', async () => {
      await act(async () => renderer.unmount());
      await act(async () => { renderer = create(React.createElement(MemoryRouter, null, React.createElement(Resume))); });
      assert.ok(text(renderer.toJSON()).includes('Son çalışılan vaka: VAKA22'));
      const link = renderer.root.findByType('a');
      assert.equal(link.props.href, '/case?patient=uuid-23&step=summary');
      assert.ok(requests.some((request) => request.url.endsWith('/patients/uuid-23') && !request.method));
    });

    await t.test('an explicit new-case route wins over an old UUID and route state without deleting saved records', async () => {
      await act(async () => renderer.unmount());
      patients.activatePatientRecord(records[0]);
      const before = requests.length;
      const Workspace = (await server.ssrLoadModule('/src/pages/SimpleCaseWorkspacePage.tsx')).default;
      await act(async () => { renderer = create(React.createElement(MemoryRouter, {
        initialEntries: [{ pathname: '/case', search: '?patient=uuid-23&new=1', state: { patientId: 'uuid-23' } }],
      }, React.createElement(Workspace))); });
      assert.equal(patients.getActivePatientId(), null);
      assert.ok(text(renderer.toJSON()).includes('Hastayı kaydet, PDF veya fotoğraf ekle, vakayı oluştur'));
      assert.ok(!text(renderer.toJSON()).includes('Existing complaint'));
      assert.equal(requests.length, before);
      assert.equal(records[0].id, 'uuid-23');
      assert.equal(records[0].case_name, 'VAKA22');
    });
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.localStorage = previous.storage; globalThis.window = previous.window; globalThis.fetch = previous.fetch;
    globalThis.IS_REACT_ACT_ENVIRONMENT = previous.act;
    await server.close();
  }
});
