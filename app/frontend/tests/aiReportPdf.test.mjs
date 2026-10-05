import assert from 'node:assert/strict';
import test from 'node:test';
import { buildAIReportPdfDefinition, createAIReportPdfBlob, exportCurrentAIReport, aiReportPdfFilename, AI_REPORT_DISCLAIMER } from '../src/services/aiReportPdf.ts';

function textOf(value) {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(textOf).join('');
  if (!value || typeof value !== 'object') return '';
  return ['text', 'stack', 'ul', 'ol', 'body'].map((key) => textOf(value[key])).join('') + textOf(value.table);
}

const report = `Öncü not: içerik kaybolmamalı.

# KLİNİK ÖZET
Türkçe: ğ Ğ ş Ş ı İ ç Ç ö Ö ü Ü.

**Ferritin:** 5 ng/mL, demir eksikliği ile uyumlu olabilir.

5. Ana değerlendirme
6. Eksik veriler

- Uyarı: tanı doğrulanmış değildir.
- *Hekim değerlendirmesi* gerekir.

| Test | Değer | Birim | Referans |
| :--- | ---: | --- | --- |
| TIBC | 445 | µg/dL | 250–450 |
| Ferritin | 5 | ng/mL | 15–150 |

HEKİM NOTU
Yeni klinik yorum eklenmemeli.`;
const date = new Date('2026-10-05T12:30:00Z');

test('PDF retains complete current text, warnings and Turkish characters without changing the input', () => {
  const input = { reportText: report, caseId: 'CASE-001', protocolNo: 'VAKA01', reportWarning: 'Önceki kayıt; güncel çıktı değildir.', createdAt: date };
  const before = structuredClone(input);
  const definition = buildAIReportPdfDefinition(input);
  const text = textOf(definition.content);
  for (const expected of ['Öncü not: içerik kaybolmamalı.', 'ğ Ğ ş Ş ı İ ç Ç ö Ö ü Ü', 'Ferritin:', '5 ng/mL', '445', '250–450', 'tanı doğrulanmış değildir.', 'Yeni klinik yorum eklenmemeli.', input.reportWarning, 'Vaka ID: CASE-001', AI_REPORT_DISCLAIMER]) assert.ok(text.includes(expected), expected);
  assert.deepEqual(input, before);
  assert.equal(definition.pageSize, 'A4');
  assert.equal(definition.defaultStyle.font, 'Roboto');
  assert.equal(definition.footer(2, 4).text, '2 / 4');
});

test('markdown headings, lists, bold, italics and table cells have structured PDF formatting', () => {
  const { content } = buildAIReportPdfDefinition({ reportText: report });
  assert.ok(content.some((node) => node.headlineLevel && node.bold && textOf(node).includes('KLİNİK ÖZET')));
  assert.ok(content.some((node) => node.headlineLevel && textOf(node).includes('HEKİM NOTU')));
  const paragraph = content.find((node) => textOf(node).includes('Ferritin:') && !node.table);
  assert.ok(paragraph.text.some((run) => run.bold && run.text === 'Ferritin:'));
  assert.ok(content.some((node) => node.ol?.length === 2 && node.start === 5));
  assert.ok(content.some((node) => node.ul?.length === 2));
  const table = content.find((node) => node.table).table;
  assert.equal(table.headerRows, 1);
  assert.equal(table.body.length, 3);
  assert.equal(textOf(table.body[1][0]), 'TIBC');
  assert.equal(table.body[1][1].alignment, 'right');
  assert.equal(table.body[0][0].bold, true);
  assert.equal(table.body[1][0].wordBreak, 'break-all');
});

test('filenames use the Istanbul export day and safely include a case identifier', () => {
  assert.equal(aiReportPdfFilename({ caseId: 'CASE-001', createdAt: date }), 'MediCore_AI_Report_CASE-001_2026-10-05.pdf');
  assert.equal(aiReportPdfFilename({ caseId: 'CASE-001', createdAt: new Date('2026-10-05T22:30:00Z') }), 'MediCore_AI_Report_CASE-001_2026-10-06.pdf');
  const name = aiReportPdfFilename({ caseId: '../../case\n:001', createdAt: date });
  assert.ok(!name.includes('/') && !name.includes('\n') && !name.includes(':'));
  assert.ok(aiReportPdfFilename({ createdAt: date }).includes('_Vaka_'));
});

test('blank reports never invoke PDF generation or download', async () => {
  for (const text of ['', '   \n']) {
    assert.throws(() => buildAIReportPdfDefinition({ reportText: text }));
    await assert.rejects(exportCurrentAIReport({ reportText: text }, { createBlob: () => assert.fail('empty report generated') }));
  }
});

test('export uses the exact existing report snapshot and never requests an AI analysis', async () => {
  const originalFetch = globalThis.fetch;
  let requests = 0;
  globalThis.fetch = async () => { requests++; throw new Error('unexpected network call'); };
  try {
    let received, downloaded;
    const input = { reportText: report, caseId: 'CASE-001', createdAt: date };
    assert.equal(await exportCurrentAIReport(input, {
      createBlob: async (snapshot) => { received = snapshot; return new Blob(['PDF']); },
      saveBlob: (blob, name) => { downloaded = { blob, name }; },
    }), true);
    assert.deepEqual(received, input);
    assert.equal(downloaded.name, 'MediCore_AI_Report_CASE-001_2026-10-05.pdf');
    assert.equal(requests, 0);
  } finally { globalThis.fetch = originalFetch; }
});

test('late PDF generation cannot download after patient or displayed report changes', async () => {
  let current = true, release;
  const ready = new Promise((resolve) => { release = resolve; });
  const operation = exportCurrentAIReport({ reportText: report }, {
    isCurrent: () => current, createBlob: async () => { await ready; return new Blob(['PDF']); },
    saveBlob: () => assert.fail('stale report downloaded'),
  });
  current = false; release();
  assert.equal(await operation, false);
  assert.equal(await exportCurrentAIReport({ reportText: report }, {
    isCurrent: () => false, createBlob: () => assert.fail('stale report generated'),
  }), false);
});

test('generation and download failures propagate without modifying the stored report', async () => {
  const input = { reportText: report };
  await assert.rejects(exportCurrentAIReport(input, { createBlob: async () => { throw new Error('font unavailable'); } }), /font unavailable/);
  await assert.rejects(exportCurrentAIReport(input, { createBlob: async () => new Blob(), saveBlob: () => { throw new Error('download failed'); } }), /download failed/);
  assert.equal(input.reportText, report);
});

test('real PDF contains embedded fonts and paginates a long report without truncating the definition', async () => {
  const longReport = `${report}\n\n` + Array.from({ length: 130 }, (_, i) => `BULGU-${i}: Şikâyet, değerlendirme ve mevcut uyarı korunur. ${'Klinik bilgi değişmez. '.repeat(12)}\n\n`).join('');
  const input = { reportText: longReport, caseId: 'CASE-001', createdAt: date };
  const text = textOf(buildAIReportPdfDefinition(input).content);
  assert.ok(text.includes('BULGU-0:') && text.includes('BULGU-129:'));
  const pdf = Buffer.from(await (await createAIReportPdfBlob(input)).arrayBuffer());
  assert.equal(pdf.subarray(0, 5).toString(), '%PDF-');
  const structure = pdf.toString('latin1');
  assert.ok((structure.match(/\/Type \/Page\b/g) ?? []).length > 4);
  assert.ok(structure.includes('/MediaBox [0 0 595.28 841.89]'));
  assert.ok(structure.includes('/FontFile2'));
});

test('untrusted HTML and image URLs are preserved as text rather than executed or fetched', () => {
  const source = '![Bulgu](https://example.invalid/private.png)\n\n<script>doNotExecute()</script>';
  const definition = buildAIReportPdfDefinition({ reportText: source });
  assert.ok(textOf(definition.content).includes('https://example.invalid/private.png'));
  assert.ok(textOf(definition.content).includes('doNotExecute()'));
  assert.ok(!JSON.stringify(definition.content).includes('"image":'));
});
