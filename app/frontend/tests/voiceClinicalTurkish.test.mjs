import assert from 'node:assert/strict';
import test from 'node:test';
import { createServer } from 'vite';

// Regression cases for spoken Turkish clinical dictation as Whisper actually transcribes it.
test('spoken Turkish clinical speech is mapped without silent misreads', async (t) => {
  const server = await createServer({ configFile: false, appType: 'custom', server: { middlewareMode: true, hmr: false, ws: false, watch: null } });
  try {
    const { turkishNumber, extractVoiceDraft } = await server.ssrLoadModule('/src/services/voiceClinicalDraft.ts');
    const draft = (text) => extractVoiceDraft(text);
    const field = (text, name) => draft(text).candidates.find((item) => item.field === name);
    const values = (text) => Object.fromEntries(draft(text).candidates.map((item) => [item.field, item.value]));

    await t.test('number grammar accepts thousands with hundreds and "buçuk" halves', () => {
      for (const [text, expected] of [['bin dokuz yüz', 1900], ['iki bin beş yüz', 2500], ['bin', 1000], ['otuz sekiz buçuk', 38.5], ['yüz kırk beş', 145],
        ['üç virgül beş', 3.5], ['İKİ YÜZ', 200], ['sıfır', 0], ['sıfır virgül sıfır beş', 0.05]]) assert.equal(turkishNumber(text), expected, text);
      for (const text of ['bir yüz', 'bir bin', 'iki otuz', 'yüz yüz', 'sıfır beş', 'otuz virgül', 'bin bin', 'otuz sekiz virgül iki buçuk']) assert.equal(turkishNumber(text), null, text);
    });

    await t.test('"buçuk" is never truncated to the whole number', () => {
      assert.equal(field('Ateşi otuz sekiz buçuk.', 'temperature').value, '38.5');
      assert.equal(field('Ateşi otuz yedi buçuk derece.', 'temperature').value, '37.5');
    });

    await t.test('dative blood pressure forms ("yüz yirmiye seksen", "on dörde dokuz", "120\'ye 80")', () => {
      assert.deepEqual(values('Tansiyon yüz yirmiye seksen.'), { systolic_bp: '120', diastolic_bp: '80' });
      assert.deepEqual(values('Tansiyon yüz kırka doksan.'), { systolic_bp: '140', diastolic_bp: '90' });
      assert.deepEqual(values("Tansiyon 120'ye 80."), { systolic_bp: '120', diastolic_bp: '80' });
      const short = draft('Tansiyon on dörde dokuz.').candidates;
      assert.equal(short.find((item) => item.field === 'systolic_bp').value, '140');
      assert.ok(short.find((item) => item.field === 'systolic_bp').issues.some((issue) => issue.includes('Kısa tansiyon')));
    });

    await t.test('blood pressure without a separator is split only when unambiguous and always flagged', () => {
      for (const [text, systolic, diastolic] of [['Tansiyonu on iki sekiz.', '120', '80'], ['Tansiyon 14 9.', '140', '90'], ['Tansiyon yüz yirmi seksen.', '120', '80']]) {
        const candidates = draft(text).candidates;
        const high = candidates.find((item) => item.field === 'systolic_bp'), low = candidates.find((item) => item.field === 'diastolic_bp');
        assert.equal(high.value, systolic, text); assert.equal(low.value, diastolic, text);
        assert.ok(high.issues.some((issue) => issue.includes('ayırıcı')), text);
      }
      // A single valid number is not a pressure pair; neither is a value interrupted by another vital.
      assert.equal(field('Tansiyon yüz on dokuz.', 'systolic_bp').value, '');
      assert.equal(field('Tansiyon yüz on dokuz.', 'diastolic_bp'), undefined);
      assert.equal(field('Tansiyon 120 nabız 80.', 'systolic_bp').value, '');
      assert.equal(field('Tansiyon 120 nabız 80.', 'heart_rate').value, '80');
    });

    await t.test('negated symptoms stay text findings and never create empty vital measurements', () => {
      for (const text of ['Ateşi olmadı.', 'Ateş yok.', 'Ateşi yoktu.']) {
        const result = draft(text);
        assert.equal(result.candidates.find((item) => item.field === 'temperature'), undefined, text);
        assert.equal(result.candidates.find((item) => item.field === 'complaints').value, text.slice(0, -1), text);
      }
      const mixed = values('Hasta karın ağrısı tarifliyor, ateşi yok.');
      assert.equal(mixed.complaints, 'Hasta karın ağrısı tarifliyor\nateşi yok');
      assert.equal(mixed.temperature, undefined);
      const conflict = field('Şikayetler: ateş var. Şikayetler: ateş olmadı.', 'complaints');
      assert.ok(conflict.issues.some((issue) => issue.includes('olumlu/olumsuz')));
      assert.equal(values('Tansiyonu yok.').history, 'Tansiyonu yok');
    });

    await t.test('common aliases: "şekeri", "nabzı dakikada", "vücut ısısı", inflected symptoms', () => {
      assert.equal(field('Şekeri yüz kırk beş.', 'glucose_mg_dl').value, '145');
      assert.equal(field('Açlık şekeri 98 miligram desilitre.', 'glucose_mg_dl').value, '98');
      assert.equal(field('Nabzı dakikada doksan.', 'heart_rate').value, '90');
      assert.equal(field('Vücut ısısı otuz sekiz.', 'temperature').value, '38');
      assert.equal(field('Üç gündür öksürüğüm var.', 'complaints').value, 'Üç gündür öksürüğüm var');
      // Diabetes is history, not a glucose reading; a mg/dL unit is not a medication.
      const diabetes = draft('Şeker hastalığı var.');
      assert.equal(diabetes.candidates.find((item) => item.field === 'glucose_mg_dl'), undefined);
      assert.equal(diabetes.candidates.find((item) => item.field === 'history').value, 'Şeker hastalığı var');
      assert.equal(values('Kan şekeri 145 miligram desilitre.').medications, undefined);
    });

    await t.test('spoken metres for height ("bir yetmiş beş", "bir metre yetmiş beş")', () => {
      for (const text of ['Boyu bir yetmiş beş.', 'Boy bir metre yetmiş beş.']) {
        const height = field(text, 'height_cm');
        assert.equal(height.value, '175', text); assert.ok(height.issues.some((issue) => issue.includes('santimetre')), text);
      }
      assert.equal(field('Boy 1.78 metre.', 'height_cm').value, '178');
    });

    await t.test('speaker turns: labels are stripped, doctor questions are never findings', () => {
      const result = draft('Doktor: Şikayetiniz nedir? Hasta: Üç gündür öksürüğüm var.');
      assert.equal(result.candidates.find((item) => item.field === 'complaints').value, 'Üç gündür öksürüğüm var');
      assert.deepEqual(result.unmapped, ['Şikayetiniz nedir']);
      // Questions without a question mark (Whisper often drops it) are still not positive findings.
      const unpunctuated = draft('Göğüs ağrınız var mı');
      assert.deepEqual(unpunctuated.candidates, []); assert.deepEqual(unpunctuated.unmapped, ['Göğüs ağrınız var mı']);
      assert.deepEqual(values('Doktor: Tansiyon yüz kırka doksan.'), { systolic_bp: '140', diastolic_bp: '90' });
    });

    await t.test('comma-separated lists stay in their dictated section; plain medication statements are recognized', () => {
      assert.equal(values('Kullandığı ilaçlar: metformin bin miligram, ramipril beş miligram.').medications, 'metformin bin miligram\nramipril beş miligram');
      assert.equal(values('Şikayetler: baş ağrısı, bulantı, ateş 38.').complaints, 'baş ağrısı\nbulantı');
      assert.equal(values('Metformin kullanıyor.').medications, 'Metformin kullanıyor');
      assert.equal(values('Sigara kullanıyor.').history, 'Sigara kullanıyor');
      // The list ends at the sentence boundary.
      assert.ok(draft('İlaçlar: aspirin. Özel bilinmeyen ifade.').unmapped.includes('Özel bilinmeyen ifade'));
    });

    await t.test('decomposed (NFD) ASR output keeps section text aligned', () => {
      const text = 'Şikayetler: göğüs ağrısı. Muayenede ödem yok.'.normalize('NFD');
      const result = values(text);
      assert.equal(result.complaints, 'göğüs ağrısı'.normalize('NFC'));
      assert.equal(result.notes, 'ödem yok'.normalize('NFC'));
    });

    await t.test('marker words inside longer words do not start a section', () => {
      const result = draft('Şikayetiniz geçti mi.');
      assert.equal(result.candidates.find((item) => item.field === 'complaints'), undefined);
    });
  } finally { await server.close(); }
});
