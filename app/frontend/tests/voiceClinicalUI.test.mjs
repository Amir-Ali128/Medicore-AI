import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { act, create } from 'react-test-renderer';
import { createServer } from 'vite';

test('voice proposals require clinical review and never auto-save', async (t) => {
  const server = await createServer({ configFile: false, appType: 'custom', server: { middlewareMode: true, hmr: false, ws: false, watch: null } });
  const original = { storage: globalThis.localStorage, window: globalThis.window, fetch: globalThis.fetch, act: globalThis.IS_REACT_ACT_ENVIRONMENT };
  const storage = new Map();
  globalThis.localStorage = { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) };
  globalThis.window = { dispatchEvent() {}, location: { hash: '#/case' } };
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const requests = [];
  globalThis.fetch = async (...args) => { requests.push(args); throw new Error('Draft UI must not make network calls'); };
  let renderer;
  const text = (node) => typeof node === 'string' ? node : (Array.isArray(node) ? node : node?.children ?? []).map(text).join('');
  const button = (name) => renderer.root.findAllByType('button').find((node) => text(node) === name);
  const label = (name) => renderer.root.findAllByType('label').find((node) => text(node) === name);
  const check = async (name, checked = true) => act(async () => label(name).findByType('input').props.onChange({ target: { checked } }));
  const approval = 'Taslağı gözden geçirdim; seçtiğim alanların forma aktarılmasını onaylıyorum.';
  try {
    const Component = (await server.ssrLoadModule('/src/components/clinical/VoiceClinicalIntake.tsx')).default;
    const { VOICE_LABELS } = await server.ssrLoadModule('/src/services/voiceClinicalDraft.ts');
    const scope = await server.ssrLoadModule('/src/services/patientScope.ts');
    scope.selectPatientScope('patient-A');
    let values = Object.fromEntries(Object.keys(VOICE_LABELS).map((field) => [field, field === 'sex' ? 'unknown' : '']));
    values = { ...values, age: '38', notes: 'Original examination' };
    const applied = [];
    const onApply = (patch) => applied.push(patch);
    const render = () => React.createElement(Component, { values, onApply });
    await act(async () => { renderer = create(render()); });
    const transcript = () => renderer.root.findAllByType('textarea').find((node) => node.props.placeholder?.startsWith('Örnek:'));
    await t.test('text creates multiple proposals while leaving form and persistence untouched', async () => {
      await act(async () => transcript().props.onChange({ target: { value: 'Hasta 65 yaşında. Nabız 108. Muayenede mukoza kuru.' } }));
      assert.ok(label('Yaş')); assert.ok(label('Nabız (bpm)')); assert.ok(label('Ek klinik not / Fizik muayene'));
      assert.equal(button('Seçili alanları forma aktar').props.disabled, true);
      assert.equal(applied.length, 0); assert.equal(values.age, '38'); assert.equal(requests.length, 0);
    });
    await t.test('an existing numeric value requires per-field overwrite permission even after general approval', async () => {
      await check('Yaş'); await check(approval);
      await act(async () => button('Seçili alanları forma aktar').props.onClick());
      assert.ok(text(renderer.root.findByProps({ role: 'alert' })).includes('alan bazında onay'));
      assert.equal(applied.length, 0);
      await check('Mevcut değeri değiştirmeyi onaylıyorum'); await check(approval);
      await act(async () => button('Seçili alanları forma aktar').props.onClick());
      assert.deepEqual(applied, [{ age: '65' }]); assert.equal(requests.length, 0);
    });
    await t.test('physical findings append to notes only when explicitly selected and approved', async () => {
      await check('Ek klinik not / Fizik muayene'); await check(approval);
      await act(async () => button('Seçili alanları forma aktar').props.onClick());
      assert.deepEqual(applied.at(-1), { notes: 'Original examination\nmukoza kuru' });
      assert.ok(text(renderer.toJSON()).includes('Kalıcı kayıt için')); assert.equal(values.notes, 'Original examination');
    });
    await t.test('changing transcript clears previous permission, selection and approval', async () => {
      await check('Yaş'); await check(approval);
      await act(async () => transcript().props.onChange({ target: { value: 'Nabız yaklaşık 110.' } }));
      assert.equal(label('Nabız (bpm)').findByType('input').props.checked, false);
      assert.equal(button('Seçili alanları forma aktar').props.disabled, true);
      assert.ok(text(renderer.toJSON()).includes('Belirsiz ifade'));
      await check('Nabız (bpm)'); await check(approval);
      await act(async () => button('Seçili alanları forma aktar').props.onClick());
      assert.ok(text(renderer.root.findByProps({ role: 'alert' })).includes('belirsizlikleri'));
      await check('Bu alanın belirsizliğini kontrol ettim'); await check(approval);
      await act(async () => button('Seçili alanları forma aktar').props.onClick());
      assert.deepEqual(applied.at(-1), { heart_rate: '110' });
    });
    await t.test('concurrent manual edits and patient changes cannot be overwritten by old proposals', async () => {
      await act(async () => transcript().props.onChange({ target: { value: 'Hasta 65 yaşında.' } }));
      await check('Yaş'); await check('Mevcut değeri değiştirmeyi onaylıyorum'); await check(approval);
      values = { ...values, age: '39' };
      await act(async () => renderer.update(render()));
      const before = applied.length;
      await act(async () => button('Seçili alanları forma aktar').props.onClick());
      assert.ok(text(renderer.root.findByProps({ role: 'alert' })).includes('Form alanı değişti')); assert.equal(applied.length, before);
      await act(async () => button('Güncel formdan taslağı yenile').props.onClick());
      await check('Yaş'); await check('Mevcut değeri değiştirmeyi onaylıyorum'); await check(approval);
      scope.selectPatientScope('patient-B');
      await act(async () => button('Seçili alanları forma aktar').props.onClick());
      assert.ok(text(renderer.root.findByProps({ role: 'alert' })).includes('Vaka değişti')); assert.equal(applied.length, before); assert.equal(requests.length, 0);
    });
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.localStorage = original.storage; globalThis.window = original.window; globalThis.fetch = original.fetch; globalThis.IS_REACT_ACT_ENVIRONMENT = original.act;
    await server.close();
  }
});
