import assert from 'node:assert/strict';
import test from 'node:test';
import { createServer } from 'vite';

test('Turkish voice extraction creates reviewable drafts without inference or writes', async (t) => {
  const server = await createServer({ configFile: false, appType: 'custom', server: { middlewareMode: true, hmr: false, ws: false, watch: null } });
  try {
    const { turkishNumber, extractVoiceDraft, approvedVoicePatch, VOICE_LABELS } = await server.ssrLoadModule('/src/services/voiceClinicalDraft.ts');
    const values = (text) => Object.fromEntries(extractVoiceDraft(text).candidates.map((item) => [item.field, item.value]));
    const blank = Object.fromEntries(Object.keys(VOICE_LABELS).map((field) => [field, field === 'sex' ? 'unknown' : '']));
    const choice = (field, value, extra = {}) => ({ field, value, mode: 'replace', overwrite: false, reviewed: false, ...extra });

    await t.test('digits and Turkish spoken numbers include explicit decimal commas', () => {
      for (const [text, expected] of [['65', 65], ['otuz yedi virgül iki', 37.2], ['yüz kırk beş', 145], ['iki yüz otuz bir', 231], ['otuz yedi virgül sıfır iki', 37.02], ['doksan', 90]]) assert.equal(turkishNumber(text), expected, text);
      for (const text of ['otuz yedi iki', 'iki yüz yüz', 'bir iki', 'bilinmiyor', 'otuz virgül']) assert.equal(turkishNumber(text), null, text);
    });
    await t.test('one dictation maps demographics, all structured vitals, symptoms, history, medicines and physical exam', () => {
      const draft = values('Altmış beş yaşında erkek. Şikayetler: iki gündür kusma. Anamnez: hipertansiyon. İlaçlar: amlodipin 5 mg. Vital bulgular: tansiyon 145/90, nabız 108, ateş 37,2, SpO2 yüzde 97, solunum 18, boy 178, kilo 82, kan şekeri 108. Muayenede ağız mukozası kuru.');
      assert.deepEqual(draft, { age: '65', sex: 'male', complaints: 'iki gündür kusma', history: 'hipertansiyon', medications: 'amlodipin 5 mg', notes: 'ağız mukozası kuru', systolic_bp: '145', diastolic_bp: '90', heart_rate: '108', temperature: '37.2', spo2: '97', respiratory_rate: '18', height_cm: '178', weight_kg: '82', glucose_mg_dl: '108' });
    });
    await t.test('section markers work in a single utterance without punctuation', () => {
      const draft = values('Hasta 65 yaşında erkek şikayetler kusma anamnez hipertansiyon ilaçlar amlodipin vital bulgular nabız 108 ateş 37.2 muayenede mukoza kuru');
      assert.equal(draft.age, '65'); assert.equal(draft.sex, 'male'); assert.equal(draft.complaints, 'kusma');
      assert.equal(draft.history, 'hipertansiyon'); assert.equal(draft.medications, 'amlodipin'); assert.equal(draft.heart_rate, '108'); assert.equal(draft.notes, 'mukoza kuru');
    });
    await t.test('conflicting numeric and sex values stay blank until explicitly corrected', () => {
      const { candidates } = extractVoiceDraft('Nabız 108. Nabız 72. Hasta erkek kadın.');
      for (const field of ['heart_rate', 'sex']) { const candidate = candidates.find((item) => item.field === field); assert.equal(candidate.value, ''); assert.ok(candidate.issues.some((issue) => issue.includes('Çelişkili'))); }
    });
    await t.test('negation/correction never chooses the retracted numeric value', () => {
      const candidate = extractVoiceDraft('Nabız 108 değil 80.').candidates.find((item) => item.field === 'heart_rate');
      assert.equal(candidate.value, ''); assert.ok(candidate.source[0].includes('108 değil 80')); assert.ok(candidate.issues.length);
    });
    await t.test('alternative numbers and explicitly opposite text statements are flagged without resolving them', () => {
      const draft = extractVoiceDraft('Nabız 108 veya 80. Şikayetler: öksürük var. Şikayetler: öksürük yok.');
      assert.equal(draft.candidates.find((item) => item.field === 'heart_rate').value, '');
      const symptoms = draft.candidates.find((item) => item.field === 'complaints');
      assert.equal(symptoms.value, 'öksürük var\nöksürük yok');
      assert.ok(symptoms.issues.some((issue) => issue.includes('Çelişkili')));
    });
    await t.test('uncertain wording, absent values and short blood pressures are flagged', () => {
      const { candidates } = extractVoiceDraft('Ateş yaklaşık 38. Nabız bilinmiyor. Tansiyon 14/9.');
      assert.equal(candidates.find((item) => item.field === 'temperature').value, '38');
      assert.ok(candidates.every((item) => item.issues.length));
      assert.equal(candidates.find((item) => item.field === 'heart_rate').value, '');
      assert.equal(candidates.find((item) => item.field === 'systolic_bp').value, '140');
    });
    await t.test('family/history/lab values cannot become current patient demographics or vitals', () => {
      const draft = values('Annesi 65 yaşında kadın, nabız 92. Laboratuvar glukoz 108. Önceki nabız 120. Vital bulgular: nabız 80.');
      assert.equal(draft.age, undefined); assert.equal(draft.sex, undefined); assert.equal(draft.glucose_mg_dl, undefined); assert.equal(draft.heart_rate, '80');
    });
    await t.test('negative findings retain their exact text; unknown expressions remain visible', () => {
      const draft = extractVoiceDraft('Muayenede ödem yok. Şikayetler: göğüs ağrısı yok. Özel bilinmeyen ifade.');
      assert.equal(draft.candidates.find((item) => item.field === 'notes').value, 'ödem yok');
      assert.equal(draft.candidates.find((item) => item.field === 'complaints').value, 'göğüs ağrısı yok');
      assert.ok(draft.unmapped.includes('Özel bilinmeyen ifade'));
      assert.equal(values('Ağız mukozası kuru. Cilt turgoru azalmış.').notes, 'Ağız mukozası kuru\nCilt turgoru azalmış');
    });
    await t.test('unit conversions are explicit, unsupported units and glued numbers require manual correction', () => {
      const draft = extractVoiceDraft('Boy 1.78 metre. Kan şekeri 5.6 mmol/L. Kilo 180 pound. Nabız onsekiz. SpO2 %97.');
      assert.equal(draft.candidates.find((item) => item.field === 'height_cm').value, '178');
      assert.equal(draft.candidates.find((item) => item.field === 'spo2').value, '97');
      for (const field of ['glucose_mg_dl', 'weight_kg', 'heart_rate']) { const candidate = draft.candidates.find((item) => item.field === field); assert.equal(candidate.value, ''); assert.ok(candidate.issues.length); }
    });
    await t.test('range violations and transcript size limits cannot be silently applied', () => {
      const draft = extractVoiceDraft('Hasta 180 yaşında. Nabız 999.');
      assert.ok(draft.candidates.every((item) => item.issues.length));
      assert.throws(() => approvedVoicePatch(blank, blank, draft.candidates, [choice('age', '180', { reviewed: true })], true));
      assert.throws(() => extractVoiceDraft('a'.repeat(12001)));
    });
    await t.test('no confirmation, no selected fields or unreviewed uncertainty means no patch', () => {
      const { candidates } = extractVoiceDraft('Nabız yaklaşık 108.');
      assert.throws(() => approvedVoicePatch(blank, blank, candidates, [choice('heart_rate', '108')], false));
      assert.throws(() => approvedVoicePatch(blank, blank, candidates, [], true));
      assert.throws(() => approvedVoicePatch(blank, blank, candidates, [choice('heart_rate', '108')], true));
      assert.deepEqual(approvedVoicePatch(blank, blank, candidates, [choice('heart_rate', '108', { reviewed: true })], true), { heart_rate: '108' });
    });
    await t.test('existing values require individual overwrite permission; current concurrent edits are protected', () => {
      const base = { ...blank, age: '38', notes: 'Original note' };
      const { candidates } = extractVoiceDraft('Hasta 65 yaşında. Muayenede mukoza kuru.');
      const before = structuredClone(base);
      assert.throws(() => approvedVoicePatch(base, base, candidates, [choice('age', '65')], true));
      assert.deepEqual(approvedVoicePatch(base, base, candidates, [choice('age', '65', { overwrite: true })], true), { age: '65' });
      assert.throws(() => approvedVoicePatch(base, { ...base, age: '39' }, candidates, [choice('age', '65', { overwrite: true })], true), /Form alanı değişti/);
      assert.deepEqual(base, before);
    });
    await t.test('text appends preserve existing data, and patches contain only explicitly selected fields', () => {
      const base = { ...blank, notes: 'Original note', complaints: 'Old complaint' };
      const { candidates } = extractVoiceDraft('Şikayetler: kusma. Muayenede mukoza kuru.');
      assert.deepEqual(approvedVoicePatch(base, base, candidates, [choice('notes', 'mukoza kuru', { mode: 'append' })], true), { notes: 'Original note\nmukoza kuru' });
      assert.equal(base.notes, 'Original note'); assert.equal(base.complaints, 'Old complaint');
      assert.throws(() => approvedVoicePatch(base, base, candidates, [choice('protocol_no', 'NEW')], true));
    });
  } finally { await server.close(); }
});
