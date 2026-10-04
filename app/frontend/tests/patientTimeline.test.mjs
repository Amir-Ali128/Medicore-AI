import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { groupPatientTimeline, timelineReportLabel } from '../src/services/patientTimelineGrouping.ts';
import { normalizeClinical } from '../src/services/clinicalRecord.ts';

const PATIENT_A = 'patient-A';
const PATIENT_B = 'patient-B';
const result = (id, name, value, unit = 'g/dL') => ({ id, test_name: name, value, unit, reference_text: '12–16' });
const entry = (id, options = {}) => ({
  id, patient_id: PATIENT_A, kind: 'laboratory', source_type: 'lab_report', source_id: `source-${id}`,
  source_path: null, title: 'Laboratuvar', date_source: 'measured_at', results: [],
  clinical: null, vital_signs: null, inferred_report_type: null, report_type_confidence: null,
  report_text: null, summary: null, file_name: null, original_file_available: false,
  ...options,
});
const response = (groups, patientId = PATIENT_A) => ({
  patient_id: patientId, groups,
  total_entries: groups.reduce((count, group) => count + group.entries.length, 0),
  total_lab_results: groups.reduce((count, group) => count + group.entries.reduce((rows, item) => rows + item.results.length, 0), 0),
});

test('timeline refuses a response for a different selected patient', () => {
  const a = response([{ date: '2026-10-02', entries: [entry('A-lab', { results: [result('A-Hb', 'Hb', 8.2)] })] }]);
  assert.throws(() => groupPatientTimeline(a, PATIENT_B), /eşleşmiyor/);
  assert.equal(groupPatientTimeline(a, PATIENT_A)[0].entries[0].results[0].value, 8.2);
});

test('every entry is checked even when the top-level patient id matches', () => {
  for (const kind of ['laboratory', 'urine_laboratory', 'lab_result_available', 'report', 'clinical', 'vital_signs']) {
    const contaminated = response([{ date: '2026-10-02', entries: [entry('A'), entry('B', { kind, patient_id: PATIENT_B })] }]);
    assert.throws(() => groupPatientTimeline(contaminated, PATIENT_A), /eşleşmiyor/, kind);
  }
});

test('same-day records share one group, newest days sort first and undated records stay last', () => {
  const source = response([
    { date: null, entries: [entry('undated', { date_source: 'unknown' })] },
    { date: '2026-08-01', entries: [entry('August')] },
    { date: '2026-10-02', entries: [entry('October-lab')] },
    { date: '2026-09-01', entries: [entry('September')] },
    { date: '2026-10-02', entries: [entry('October-report', { kind: 'report' }), entry('October-clinical', { kind: 'clinical' }), entry('October-vitals', { kind: 'vital_signs' }), entry('October-urine', { kind: 'urine_laboratory' })] },
  ]);
  const before = structuredClone(source);
  const grouped = groupPatientTimeline(source, PATIENT_A);
  assert.deepEqual(grouped.map((group) => group.date), ['2026-10-02', '2026-09-01', '2026-08-01', null]);
  assert.deepEqual(grouped[0].entries.map((item) => item.kind), ['laboratory', 'report', 'clinical', 'vital_signs', 'urine_laboratory']);
  assert.deepEqual(source, before, 'view grouping must not rewrite the source response');
});

test('older Hb values remain distinct and all 50 parameters remain reachable', () => {
  const fifty = Array.from({ length: 50 }, (_, index) => result(`row-${index}`, `Parameter ${index + 1}`, index));
  const source = response([
    { date: '2026-08-01', entries: [entry('August', { results: [result('aug-Hb', 'Hb', 12.1)] })] },
    { date: '2026-09-01', entries: [entry('September', { results: [result('sep-Hb', 'Hb', 13)] })] },
    { date: '2026-10-01', entries: [entry('October', { results: [result('oct-Hb', 'Hb', 13.8)] }), entry('50-results', { results: fifty })] },
  ]);
  const grouped = groupPatientTimeline(source, PATIENT_A);
  assert.deepEqual(grouped.flatMap((group) => group.entries.flatMap((item) => item.results.filter((row) => row.test_name === 'Hb').map((row) => row.value))), [13.8, 13, 12.1]);
  assert.equal(grouped[0].entries[1].results.length, 50);
  assert.deepEqual(grouped[0].entries[1].results.map((row) => row.id), fifty.map((row) => row.id));
  assert.equal(source.total_lab_results, 53);
});

test('semantic date fields survive grouping and late result notices do not duplicate result counts', () => {
  const lab = entry('sample-2', { event_date: '2026-10-02', specimen_date: '2026-10-02', result_date: '2026-10-04', uploaded_at: '2026-10-04', date_source: 'specimen_date', results: [result('ferritin', 'Ferritin', 5)] });
  const notice = entry('available-4', { kind: 'lab_result_available', source_id: lab.source_id, result_ids: ['ferritin'], event_date: '2026-10-02', specimen_date: '2026-10-02', result_date: '2026-10-04', date_source: 'result_date' });
  const source = response([
    { date: '2026-10-02', entries: [lab, entry('ultrasound', { kind: 'report', event_date: '2026-10-02', document_date: '2026-10-03', uploaded_at: '2026-10-04', date_source: 'exam_date' })] },
    { date: '2026-10-04', entries: [notice] },
    { date: '2026-10-03', entries: [entry('consultation', { kind: 'report', event_date: '2026-10-03', document_date: '2026-10-03', date_source: 'document_date' })] },
  ]);
  const grouped = groupPatientTimeline(source, PATIENT_A);
  assert.deepEqual(grouped.map((group) => group.date), ['2026-10-04', '2026-10-03', '2026-10-02']);
  assert.deepEqual(grouped[2].entries[0], lab);
  assert.deepEqual(grouped[0].entries[0].results, []);
  assert.deepEqual(grouped[0].entries[0].result_ids, ['ferritin']);
  assert.equal(source.total_lab_results, 1);
});

test('derived report types have readable labels and weak or unrecognized types fall back to Rapor', () => {
  for (const [type, label] of [['CT', 'BT / Tomografi'], ['ULTRASOUND', 'Ultrason / USG'], ['MRI', 'MR'], ['X_RAY', 'Röntgen'], ['PATHOLOGY', 'Patoloji'], ['ECHOCARDIOGRAPHY', 'Ekokardiyografi'], ['ENDOSCOPY', 'Endoskopi'], ['OTHER', 'Diğer Rapor']]) {
    assert.equal(timelineReportLabel(type), label);
  }
  for (const type of ['UNKNOWN', 'unsupported-type', null]) assert.equal(timelineReportLabel(type), 'Rapor');
});

test('timeline API selection checks, abort propagation and UI rendering', async (t) => {
  const server = await createServer({ configFile: false, appType: 'custom', server: { middlewareMode: true, hmr: false, ws: false, watch: null } });
  const originals = { storage: globalThis.localStorage, window: globalThis.window, fetch: globalThis.fetch };
  globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
  globalThis.window = { location: { hash: '#/patient-timeline' } };
  const json = (body) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
  try {
    const { getPatientHealthTimeline } = await server.ssrLoadModule('/src/services/patientTimelineClient.ts');
    const { PatientTimelineContent } = await server.ssrLoadModule('/src/components/patient/PatientTimelinePanel.tsx');
    const render = (timeline) => renderToStaticMarkup(React.createElement(PatientTimelineContent, { timeline }));

    await t.test('request uses explicit selected patient and passes cancellation signal', async () => {
      const controller = new AbortController();
      let requested;
      globalThis.fetch = async (url, init) => {
        requested = { url, signal: init.signal, method: init.method };
        return json(response([{ date: '2026-08-01', entries: [entry('old')] }, { date: '2026-10-02', entries: [entry('new')] }]));
      };
      const loaded = await getPatientHealthTimeline(PATIENT_A, controller.signal);
      assert.ok(requested.url.endsWith(`/timeline/patients/${PATIENT_A}/health-history`));
      assert.equal(requested.method, 'GET');
      assert.equal(requested.signal, controller.signal);
      assert.deepEqual(loaded.groups.map((group) => group.date), ['2026-10-02', '2026-08-01']);
    });

    await t.test('late A response cannot be accepted by a request for B', async () => {
      let release;
      globalThis.fetch = async () => new Promise((resolve) => { release = resolve; });
      const loadingB = getPatientHealthTimeline(PATIENT_B);
      release(json(response([{ date: '2026-10-02', entries: [entry('A-lab', { results: [result('A-Hb', 'Hb', 8.2), result('A-CRP', 'CRP', 120)] })] }])));
      await assert.rejects(loadingB, /eşleşmiyor/);
      globalThis.fetch = async () => json(response([{ date: '2026-10-02', entries: [entry('B-lab', { patient_id: PATIENT_B, results: [result('B-Hb', 'Hb', 15.1), result('B-CRP', 'CRP', 2)] })] }], PATIENT_B));
      const b = await getPatientHealthTimeline(PATIENT_B);
      assert.deepEqual(b.groups[0].entries[0].results.map((row) => row.value), [15.1, 2]);
      const html = render(b);
      assert.ok(html.includes('15.1'));
      assert.ok(!html.includes('8.2'));
      assert.ok(!html.includes('120'));
    });

    await t.test('cancelling a pending timeline request rejects without exposing data', async () => {
      const controller = new AbortController();
      globalThis.fetch = async (_url, init) => new Promise((_resolve, reject) => {
        init.signal.addEventListener('abort', () => reject(new DOMException('Cancelled', 'AbortError')), { once: true });
      });
      const loading = getPatientHealthTimeline(PATIENT_A, controller.signal);
      controller.abort();
      await assert.rejects(loading, { name: 'AbortError' });
    });

    await t.test('all 50 lab rows render including zero, unit and reference range', () => {
      const rows = Array.from({ length: 50 }, (_, index) => result(`row-${index}`, `Test ${index + 1}`, index));
      const html = render(response([{ date: '2026-10-02', entries: [entry('50-lab', { results: rows })] }]));
      assert.ok(html.includes('Tüm sonuçları göster (50)'));
      assert.equal((html.match(/<tr/g) ?? []).length, 51, '50 rows plus the table header');
      for (let index = 1; index <= 50; index++) assert.ok(html.includes(`>Test ${index}</td>`), `Test ${index}`);
      assert.ok(html.includes('>0</td>'));
      assert.ok(html.includes('>g/dL</td>'));
      assert.ok(html.includes('>12–16</td>'));
    });

    await t.test('Vaka 1 shows October 2 sample, October 3 consultation and October 4 late results distinctly', () => {
      const dates = { event_date: '2026-10-02', specimen_date: '2026-10-02', result_date: '2026-10-04', uploaded_at: '2026-10-04' };
      const ironRows = [
        { ...result('ferritin', 'Ferritin', 5, 'ng/mL'), ...dates, status: 'LOW', reference_text: '15–150' },
        { ...result('iron', 'Serum demir', 22, 'µg/dL'), ...dates, status: 'LOW', reference_text: '50–170' },
        { ...result('tibc', 'TIBC', 445, 'µg/dL'), ...dates, status: 'NORMAL', source_flag: 'High', reference_text: '250–450' },
        { ...result('tsat', 'TSAT', 5, '%'), ...dates, status: 'LOW', reference_text: '15–45' },
      ];
      const lab = entry('sample-2', { ...dates, date_source: 'specimen_date', results: ironRows });
      const notice = entry('late-4', { ...dates, kind: 'lab_result_available', source_id: lab.source_id, title: 'Geciken laboratuvar sonuçları', date_source: 'result_date', result_ids: ironRows.map((row) => row.id) });
      const source = response([
        { date: '2026-10-02', entries: [lab, entry('usg-2', { kind: 'report', source_type: 'radiology_report', inferred_report_type: 'ULTRASOUND', event_date: '2026-10-02', document_date: '2026-10-03', uploaded_at: '2026-10-04', date_source: 'exam_date', report_text: 'İntramural miyom' }), entry('clinical-2', { kind: 'clinical', title: 'Klinik Öykü', event_date: '2026-10-02', clinical: normalizeClinical({ complaints: ['Yoğun adet kanaması'] }) }), entry('vital-2', { kind: 'vital_signs', title: 'Vital Bulgular', event_date: '2026-10-02', vital_signs: { heart_rate: 108 } })] },
        { date: '2026-10-03', entries: [entry('consultation-3', { kind: 'report', source_type: 'radiology_report', document_date: '2026-10-03', uploaded_at: '2026-10-04', date_source: 'document_date', report_text: 'Kadın doğum konsültasyonu: menoraji.' })] },
        { date: '2026-10-04', entries: [notice] },
      ]);
      const html = render({ ...source, groups: groupPatientTimeline(source, PATIENT_A) });
      assert.equal((html.match(/<section/g) ?? []).length, 3);
      assert.ok(html.indexOf('>4 Ekim 2026</h2>') < html.indexOf('>3 Ekim 2026</h2>'));
      assert.ok(html.indexOf('>3 Ekim 2026</h2>') < html.indexOf('>2 Ekim 2026</h2>'));
      for (const text of ['Örnek: 2 Ekim 2026', 'Sonuç: 4 Ekim 2026', 'Yükleme: 4 Ekim 2026', 'Muayene: 2 Ekim 2026', 'Belge: 3 Ekim 2026', 'Geciken laboratuvar sonuçları', 'Kadın doğum konsültasyonu', 'Vital Bulgular', 'İntramural miyom']) assert.ok(html.includes(text), text);
      assert.ok(html.includes('aria-controls="timeline-sample-2"'));
      assert.ok(!html.includes('href="#timeline-'), 'scrolling must preserve the application hash route');
      assert.equal((html.match(/>Normal<\/span>/g) ?? []).length, 2, 'TIBC is NORMAL in the clinical source and its availability notice');
      assert.ok(!html.includes('>Yüksek</span>'), 'raw High flags must not override canonical status');
      assert.equal(source.total_lab_results, 4);
      assert.deepEqual(notice.results, []);
    });

    await t.test('late result references cannot resolve rows from another source or duplicate an id', () => {
      const lab = entry('original', { results: [{ ...result('same-id', 'Ferritin', 5), status: 'LOW' }] });
      const unknown = entry('notice-unknown', { kind: 'lab_result_available', source_id: 'another-source', result_ids: ['same-id'], title: 'Unresolved notice' });
      const duplicate = entry('notice-duplicate', { kind: 'lab_result_available', source_id: lab.source_id, result_ids: ['same-id', 'same-id'], title: 'Resolved notice' });
      const html = render(response([{ date: '2026-10-04', entries: [unknown, duplicate] }, { date: '2026-10-02', entries: [lab] }]));
      const unresolvedHtml = html.split('id="timeline-notice-unknown"')[1].split('</article>')[0];
      assert.ok(!unresolvedHtml.includes('Ferritin'));
      assert.ok(unresolvedHtml.includes('Sonuç ayrıntıları ilgili laboratuvar kaydında bulunur.'));
      const resolvedHtml = html.split('id="timeline-notice-duplicate"')[1].split('</article>')[0];
      assert.equal((resolvedHtml.match(/>Ferritin</g) ?? []).length, 1);
      assert.ok(resolvedHtml.includes('aria-controls="timeline-original"'));
    });

    await t.test('qualitative and legacy lab rows never invent HIGH or LOW from text', () => {
      const rows = [
        { ...result('qualitative', 'Kültür', 'Negatif', null), status: 'UNKNOWN', source_flag: 'High', raw_reference: 'Negatif' },
        { ...result('legacy', 'Eski kayıt', 445, 'µg/dL'), reference_text: '250–450' },
      ];
      const html = render(response([{ date: '2026-10-02', entries: [entry('unknown-status', { results: rows })] }]));
      assert.equal((html.match(/>Değerlendirilemedi<\/span>/g) ?? []).length, 2);
      assert.ok(!html.includes('>Yüksek</span>'));
      assert.ok(!html.includes('>Düşük</span>'));
      assert.ok(html.includes('>Negatif</td>'));
    });

    await t.test('report view preserves complete original text and UNKNOWN never invents a modality', () => {
      const fullText = 'Bulgular: Her iki böbrek normal.\nSonuç: <kontrol> & takip önerilir.\nRaporun son satırı.';
      const record = entry('report', { kind: 'report', source_type: 'radiology_report', title: 'Belirsiz rapor', inferred_report_type: 'UNKNOWN', report_text: fullText, summary: 'Kısa özet', file_name: 'original.pdf' });
      const source = response([{ date: '2026-10-02', entries: [record] }]);
      const html = render(source);
      assert.ok(html.includes('>Rapor</h3>'));
      assert.ok(html.includes('Raporu Gör'));
      assert.ok(html.includes('Bulgular: Her iki böbrek normal.\nSonuç: &lt;kontrol&gt; &amp; takip önerilir.\nRaporun son satırı.'));
      assert.ok(html.includes('original.pdf'));
      assert.ok(!html.includes('Kısa özet'));
      assert.ok(!html.includes('Tomografi'));
      assert.equal(record.report_text, fullText);
    });

    await t.test('clinical history and separate compact vitals share one day without an empty-history message', () => {
      const clinical = normalizeClinical({ complaints: ['kusma', 'ağız kuruluğu'], history: ['Hipertansiyon'], medications: ['amlodipin 5 mg/gün'], notes: 'Cilt turgoru azalmış' });
      const vitals = { systolic_bp: 145, diastolic_bp: 90, heart_rate: 108, temperature: 37.2, spo2: 97, respiratory_rate: 18, height_cm: 178, weight_kg: 82, glucose_mg_dl: 0 };
      const html = render(response([{ date: '2026-10-02', entries: [entry('clinical', { kind: 'clinical', source_type: 'patient', title: 'Klinik Öykü', clinical }), entry('vitals', { kind: 'vital_signs', source_type: 'patient', title: 'Vital Bulgular', vital_signs: vitals })] }]));
      for (const text of ['Şikayetler', 'kusma\nağız kuruluğu', 'Hipertansiyon', 'amlodipin 5 mg/gün', 'Cilt turgoru azalmış', 'Vital Bulgular', 'TA 145/90 mmHg', 'Nabız 108/dk', 'Ateş 37.2°C', 'SpO₂ %97', 'Solunum 18/dk', 'Boy 178 cm', 'Kilo 82 kg', 'Kan şekeri 0 mg/dL']) assert.ok(html.includes(text), text);
      assert.ok(!html.includes('Henüz klinik bilgi eklenmedi'));
      assert.equal((html.match(/<section/g) ?? []).length, 1);
    });

    await t.test('undated sources and explicit record-date fallback remain visible', () => {
      const html = render(response([{ date: null, entries: [entry('undated', { title: 'Tarihsiz laboratuvar', date_source: 'created_at', results: [result('undated-result', 'Hb', 12.1)] })] }]));
      assert.ok(html.includes('Tarihi belirtilmemiş kayıtlar'));
      assert.ok(html.includes('Kayıt tarihi'));
      assert.ok(html.includes('Tarihsiz laboratuvar'));
      assert.ok(html.includes('12.1'));
      assert.ok(render(response([])).includes('Bu hasta için kayıtlı sağlık geçmişi bulunmuyor.'));
    });

    await t.test('upload and recorded date fallbacks never pretend to be clinical event dates', () => {
      for (const source of ['created_at', 'clinical_recorded_at', 'vitals_recorded_at', 'clinical_context_recorded_at']) {
        const html = render(response([{ date: '2026-10-04', entries: [entry(`fallback-${source}`, { event_date: '2026-10-04', date_source: source })] }]));
        assert.ok(html.includes('Kayıt tarihi'), source);
        assert.ok(html.includes('Kayıt: 4 Ekim 2026'), source);
        assert.ok(!html.includes('Klinik olay:'), source);
      }
      const uploaded = render(response([{ date: '2026-10-04', entries: [entry('uploaded', { event_date: '2026-10-04', uploaded_at: '2026-10-04', date_source: 'uploaded_at' })] }]));
      assert.ok(uploaded.includes('Kayıt tarihi'));
      assert.ok(uploaded.includes('Yükleme: 4 Ekim 2026'));
      assert.ok(!uploaded.includes('Klinik olay:'));
      assert.ok(!uploaded.includes('Kayıt: 4 Ekim 2026'), 'the same upload date does not need a duplicate record label');
    });
  } finally {
    globalThis.localStorage = originals.storage;
    globalThis.window = originals.window;
    globalThis.fetch = originals.fetch;
    await server.close();
  }
});
