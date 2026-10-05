import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { act, create } from 'react-test-renderer';
import { createServer } from 'vite';

test('PDF button exports the displayed report without AI calls, handles failures and patient changes', async (t) => {
  const server = await createServer({ configFile: false, appType: 'custom', server: { middlewareMode: true, hmr: false, ws: false, watch: null } });
  const previous = { storage: globalThis.localStorage, fetch: globalThis.fetch, document: globalThis.document, act: globalThis.IS_REACT_ACT_ENVIRONMENT, url: URL.createObjectURL, revoke: URL.revokeObjectURL };
  const storage = new Map();
  let clicks = [], requests = 0;
  globalThis.localStorage = { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) };
  globalThis.fetch = async () => { requests++; throw new Error('PDF must not call AI/backend'); };
  globalThis.document = { createElement: () => ({ href: '', download: '', remove() {}, click() { clicks.push(this.download); } }), body: { appendChild() {} } };
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  URL.createObjectURL = () => 'blob:pdf-test';
  URL.revokeObjectURL = () => {};
  const timers = globalThis.setTimeout;
  // Preserve short runtime timers, but don't leave a 60-second URL cleanup
  // timer holding the Node test process open.
  globalThis.setTimeout = (callback, delay, ...args) => { const timer = timers(callback, delay, ...args); if (delay === 60_000) timer.unref(); return timer; };
  let renderer;
  try {
    const Button = (await server.ssrLoadModule('/src/components/clinical/AIReportPdfDownloadButton.tsx')).default;
    const scope = await server.ssrLoadModule('/src/services/patientScope.ts');
    scope.selectPatientScope('case-A');
    const reportText = '# Klinik Özet\n\nHalsizlik, TIBC **445** µg/dL; NORMAL.\n\nHekim notu: kaynak veri korunur.';
    await act(async () => { renderer = create(React.createElement(Button, { reportText: null, caseId: 'case-A' })); });
    await t.test('missing and blank reports disable download', async () => {
      assert.equal(renderer.root.findByType('button').props.disabled, true);
      await act(async () => { renderer.update(React.createElement(Button, { reportText: '  ', caseId: 'case-A' })); });
      assert.equal(renderer.root.findByType('button').props.disabled, true);
    });
    await t.test('existing report downloads once with no AI/provider request', async () => {
      await act(async () => { renderer.update(React.createElement(Button, { reportText, caseId: 'case-A', protocolNo: 'CASE-001' })); });
      await act(async () => { await renderer.root.findByType('button').props.onClick(); });
      assert.equal(clicks.length, 1);
      assert.match(clicks[0], /^MediCore_AI_Report_CASE-001_\d{4}-\d{2}-\d{2}\.pdf$/);
      assert.equal(requests, 0);
      assert.equal(renderer.root.findByType('button').props.disabled, false);
    });
    await t.test('download errors are readable and allow retry while report remains available', async () => {
      URL.createObjectURL = () => { throw new Error('browser download rejected'); };
      await act(async () => { await renderer.root.findByType('button').props.onClick(); });
      const alert = renderer.root.findByProps({ role: 'alert' });
      assert.ok(alert.children.join('').includes('mevcut AI raporunuz korunuyor'));
      assert.equal(renderer.root.findByType('button').props.disabled, false);
      URL.createObjectURL = () => 'blob:pdf-test';
      await act(async () => { await renderer.root.findByType('button').props.onClick(); });
      assert.equal(renderer.root.findAllByProps({ role: 'alert' }).length, 0);
      assert.equal(clicks.length, 2);
    });
    await t.test('changing patient during export prevents the old report download', async () => {
      let pending;
      await act(async () => {
        pending = renderer.root.findByType('button').props.onClick();
        scope.selectPatientScope('case-B');
        await pending;
      });
      assert.equal(clicks.length, 2);
      assert.equal(requests, 0);
    });
  } finally {
    if (renderer) await act(async () => { renderer.unmount(); });
    globalThis.localStorage = previous.storage; globalThis.fetch = previous.fetch;
    globalThis.document = previous.document; globalThis.IS_REACT_ACT_ENVIRONMENT = previous.act;
    URL.createObjectURL = previous.url; URL.revokeObjectURL = previous.revoke;
    globalThis.setTimeout = timers;
    await server.close();
  }
});
