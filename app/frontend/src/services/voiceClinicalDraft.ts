import { VITAL_FIELDS } from './clinicalRecord';

export type VoiceField = 'age' | 'sex' | 'complaints' | 'history' | 'medications' | 'notes' | typeof VITAL_FIELDS[number]['key'];
export type VoiceForm = Record<VoiceField, string>;
export type VoiceCandidate = { field: VoiceField; value: string; source: string[]; issues: string[]; alternatives: string[] };
export const VOICE_LABELS: Record<VoiceField, string> = {
  age: 'Yaş', sex: 'Cinsiyet', complaints: 'Şikayetler', history: 'Özgeçmiş / Hastalıklar',
  medications: 'İlaçlar', notes: 'Ek klinik not / Fizik muayene',
  ...Object.fromEntries(VITAL_FIELDS.map((field) => [field.key, `${field.label} (${field.unit})`])),
} as Record<VoiceField, string>;
const TEXT_FIELDS = new Set<VoiceField>(['complaints', 'history', 'medications', 'notes']);
export const isVoiceTextField = (field: VoiceField) => TEXT_FIELDS.has(field);
const normalize = (value: string) => value.toLocaleLowerCase('tr-TR').replace(/ı/g, 'i').normalize('NFD').replace(/\p{M}/gu, '');
const UNITS: Record<string, number> = { sifir: 0, bir: 1, iki: 2, uc: 3, dort: 4, bes: 5, alti: 6, yedi: 7, sekiz: 8, dokuz: 9 };
const TENS: Record<string, number> = { on: 10, yirmi: 20, otuz: 30, kirk: 40, elli: 50, altmis: 60, yetmis: 70, seksen: 80, doksan: 90 };
const WORD = `(?:${[...Object.keys(UNITS), ...Object.keys(TENS), 'yuz', 'bin'].join('|')})`;
const INTEGER = `(?:\\d+|${WORD}(?:\\s+${WORD}){0,6})`;
const NUMBER = `${INTEGER}(?:\\s*(?:[.,]|virgul|nokta)\\s*(?:\\d+|${WORD}(?:\\s+${WORD})?)|\\s+bucuk)?`;
// "yüz yirmiye seksen", "on dörde dokuz", "120'ye 80": the dative suffix acts as the separator.
const DATIVE: Record<string, string> = {
  bire: 'bir', ikiye: 'iki', uce: 'uc', dorde: 'dort', bese: 'bes', altiya: 'alti', yediye: 'yedi', sekize: 'sekiz', dokuza: 'dokuz',
  ona: 'on', yirmiye: 'yirmi', otuza: 'otuz', kirka: 'kirk', elliye: 'elli', altmisa: 'altmis', yetmise: 'yetmis', seksene: 'seksen', doksana: 'doksan', yuze: 'yuz',
};
// Spoken polarity right after a symptom/vital word: a statement, never a measurement.
const POLARITY = '(?:var(?:di|mis)?|yok(?:tu|mus)?|oldu|olmadi|olmamis|olmuyor|mevcut|degil|cikti|cikmadi|yukseldi|yukselmedi)';
const SPEAKER = /^\s*(?:(doktor|dr|hekim|hemsire)|(hasta yakini|hasta|refakatci))\s*:\s*/;
const QUESTION_TAIL = /\b(?:mi|mu|misin|musun|misiniz|musunuz|midir|mudur|miydi|muydu|nedir|ne zaman|nasil|nerede|hangi)\s*$/;

function integerWords(text: string): number | null {
  const tokens = text.trim().split(/\s+/);
  if (!tokens[0]) return null;
  if (tokens.length === 1 && tokens[0] === 'sifir') return 0;
  // Group grammar (< 1000): [unit] [yüz] [tens] [unit]; "bin" may follow a group once.
  let total = 0, group = 0, pending = 0, stage = 0, thousands = false;
  for (const token of tokens) {
    if (token === 'sifir') return null;
    if (token === 'bin') {
      if (thousands) return null;
      const multiplier = stage === 0 ? 1 : group + pending;
      if ((stage === 1 && pending === 1) || multiplier < 1) return null;
      total = multiplier * 1000; group = 0; pending = 0; stage = 0; thousands = true;
    } else if (token === 'yuz') {
      if (stage === 0) group = 100;
      else if (stage === 1 && pending > 1) { group = pending * 100; pending = 0; }
      else return null;
      stage = 2;
    } else if (token in TENS) {
      if (stage !== 0 && stage !== 2) return null;
      group += TENS[token]; stage = 3;
    } else if (token in UNITS) {
      if (stage === 0) { pending = UNITS[token]; stage = 1; }
      else if (stage === 2 || stage === 3) { group += UNITS[token]; stage = 4; }
      else return null;
    } else return null;
  }
  return total + group + pending;
}

/** Restricted Turkish number grammar: reject malformed sequences, never guess. */
export function turkishNumber(value: string): number | null {
  let normalized = normalize(value.trim()).replace(/\s+/g, ' ');
  if (/^\d+(?:[.,]\d+)?$/.test(normalized)) return Number(normalized.replace(',', '.'));
  const half = /\s+bucuk$/.test(normalized);
  if (half) normalized = normalized.replace(/\s+bucuk$/, '');
  const pieces = normalized.split(/\s*(?:virgul|nokta|[.,])\s*/);
  if (pieces.length > 2 || (half && pieces.length > 1)) return null;
  const whole = /^\d+$/.test(pieces[0]) ? Number(pieces[0]) : integerWords(pieces[0]);
  if (whole === null) return null;
  if (half) return whole + 0.5;
  if (pieces.length === 1) return whole;
  if (!pieces[1]) return null;
  const fraction = /^\d+$/.test(pieces[1]) ? pieces[1] : pieces[1].split(/\s+/).every((word) => word in UNITS)
    ? pieces[1].split(/\s+/).map((word) => UNITS[word]).join('') : String(integerWords(pieces[1]) ?? '');
  return /^\d+$/.test(fraction) ? Number(`${whole}.${fraction}`) : null;
}

/** Blood pressure spoken without a separator ("on iki sekiz", "14 9", "yüz yirmi seksen"): accept only one unambiguous split. */
function unseparatedPressure(sequence: string): [number, number] | null {
  const tokens = sequence.trim().split(/\s+/);
  if (tokens.length < 2 || turkishNumber(sequence) !== null) return null;
  const digits = tokens.every((token) => /^\d+$/.test(token));
  if (!digits && tokens.some((token) => /\d/.test(token))) return null;
  const splits: Array<[number, number]> = [];
  for (let index = 1; index < tokens.length; index++) {
    const left = tokens.slice(0, index).join(' '), right = tokens.slice(index).join(' ');
    const systolic = digits ? (index === 1 ? Number(left) : null) : integerWords(left);
    const diastolic = digits ? (tokens.length - index === 1 ? Number(right) : null) : integerWords(right);
    if (systolic !== null && diastolic !== null && systolic > diastolic && diastolic > 0) splits.push([systolic, diastolic]);
  }
  return splits.length === 1 ? splits[0] : null;
}

export function validateVoiceValue(field: VoiceField, value: string): string | null {
  if (!value.trim()) return 'Değer boş olamaz.';
  if (isVoiceTextField(field)) return value.length <= 6000 ? null : 'Metin çok uzun.';
  if (field === 'sex') return ['male', 'female', 'other'].includes(value) ? null : 'Cinsiyeti seçin.';
  if (!/^\d+(?:[.,]\d+)?$/.test(value)) return 'Geçerli bir sayı girin.';
  const number = Number(value.replace(',', '.'));
  if (field === 'age') return Number.isInteger(number) && number >= 0 && number <= 130 ? null : 'Yaş 0–130 arasında tam sayı olmalı.';
  const rule = VITAL_FIELDS.find((item) => item.key === field)!;
  return number >= rule.min && number <= rule.max ? null : `${rule.min}–${rule.max} ${rule.unit} aralığını kontrol edin.`;
}

type Clause = { source: string; question: boolean; sentence: number };
const MARKER = /\b(?:sikayet(?:i|ler(?:i)?)?|semptomlar|ozgecmis|anamnez|aile oykusu|ilaclar(?:i)?|kullandigi ilaclar|fizik muayene|muayenede|ek klinik not|vital bulgular)\b/g;

/** Sentences keep their end mark so questions can be told apart; commas split clauses inside a sentence. */
function splitClauses(transcript: string): Clause[] {
  const clauses: Clause[] = [];
  const parts = transcript.split(/([;\n!?]+|\.(?!\d))/u);
  for (let index = 0, sentence = 0; index < parts.length; index += 2, sentence++) {
    const question = (parts[index + 1] ?? '').includes('?');
    for (const piece of parts[index].split(/,(?!\d)/u)) {
      const starts = [0, ...[...normalize(piece).matchAll(MARKER)].map((match) => match.index!).filter((start) => start > 0)];
      for (const [position, start] of starts.entries()) {
        const source = piece.slice(start, starts[position + 1] ?? piece.length).trim();
        if (source) clauses.push({ source, question, sentence });
      }
    }
  }
  return clauses;
}

/** Extraction only: preserve dictated text, explicit negation and source evidence. */
export function extractVoiceDraft(input: string): { candidates: VoiceCandidate[]; unmapped: string[] } {
  if (input.length > 12000) throw new Error('Transkripsiyon çok uzun; metni daha kısa bölümlere ayırın.');
  // Decomposed (NFD) ASR output would shift normalized indices against the original text.
  const transcript = input.normalize('NFC');
  const found: Array<{ field: VoiceField; value: string; source: string; issues: string[] }> = [];
  const unmapped: string[] = [];
  function add(field: VoiceField, value: string, source: string, issues: string[] = []) {
    const invalid = value ? validateVoiceValue(field, value) : null;
    found.push({ field, value, source, issues: [...issues, ...(invalid ? [invalid] : []), ...(!value ? ['Değer belirlenemedi; elle doğrulayın.'] : [])] });
  }
  let familyContext = false;
  let section: { field: VoiceField; sentence: number } | null = null;
  for (const clause of splitClauses(transcript)) {
    // Speaker labels ("Doktor:", "Hasta:") are turn metadata, not clinical content.
    const speaker = normalize(clause.source).match(SPEAKER);
    const source = speaker ? clause.source.slice(speaker[0].length).trim() : clause.source;
    if (!source) continue;
    const text = normalize(source);
    // Questions ("Göğüs ağrınız var mı?") are not findings; keep them visible but never map them.
    if (clause.question || QUESTION_TAIL.test(text)) { unmapped.push(source); continue; }
    if (section && section.sentence !== clause.sentence) section = null;
    if (/\b(?:hasta(?:nin)?|vital bulgular|fizik muayene|muayenede)\b/.test(text)) familyContext = false;
    if (/\b(?:annesi|anne|babasi|baba|kardesi|kardes|aile oykusu)\b/.test(text)) familyContext = true;
    const start = found.length;
    const issues = /\b(?:yaklasik|sanirim|galiba|muhtemelen|olabilir|emin degilim|belki|tahminen|civarinda)\b/.test(text) ? ['Belirsiz ifade: hekim doğrulaması gerekli.'] : [];
    const correction = /\b(?:degil|yerine|duzelt|iptal|ya da|veya)\b/.test(text);
    const numericIssues = [...issues, ...(correction ? ['Olumsuzlama, düzeltme veya alternatif değer var; doğru değeri elle girin.'] : [])];
    // Explicit historical/family/laboratory sections cannot set patient vitals.
    const historical = familyContext || /\b(?:ozgecmis|anamnez|laboratuvar|gecen yil|gecen hafta|gecen ay|dun|onceki)\b/.test(text);
    const asNumber = (raw: string) => { const value = turkishNumber(raw); return value === null || correction ? '' : String(value); };
    if (!historical) {
      for (const pattern of [new RegExp(`(${NUMBER})\\s+yas(?:inda|indaki|i|inda)?\\b`, 'g'), new RegExp(`\\byas(?:i)?\\s*[:=]?\\s*(${NUMBER})`, 'g')]) {
        for (const match of text.matchAll(pattern)) add('age', asNumber(match[1]), source, numericIssues);
      }
      for (const match of text.matchAll(/\b(erkek|kadin|bayan)\b/g)) add('sex', correction ? '' : match[1] === 'erkek' ? 'male' : 'female', source, numericIssues);
      // Dative separators: "yüz yirmiye seksen" → "yüz yirmi bolu seksen", "120'ye 80" → "120 bolu 80".
      const pressureText = text
        .replace(new RegExp(`\\b(${Object.keys(DATIVE).join('|')})\\s+(?=${INTEGER}\\b)`, 'g'), (_all, word: string) => `${DATIVE[word]} bolu `)
        .replace(/\b(\d+)\s*['’]?\s*(?:y?e|y?a)\s+(?=\d)/g, '$1 bolu ');
      const bpLabel = '(?:tansiyon(?:u)?(?:\\s+degeri)?|kan basinci|ta)\\s*[:=]?\\s*(?:(?:yaklasik|sanirim|galiba)\\s*)?';
      const bp = new RegExp(`\\b${bpLabel}(${NUMBER})\\s*(?:/|bolu|uzeri)\\s*(${NUMBER})`, 'g');
      let bloodPressure = false;
      const addPressure = (systolicRaw: string, diastolicRaw: string, tail: string, extra: string[]) => {
        bloodPressure = true;
        let systolic = systolicRaw, diastolic = diastolicRaw;
        const short = systolic && diastolic && Number(systolic) <= 30 && Number(diastolic) <= 20;
        if (short) { systolic = String(Number(systolic) * 10); diastolic = String(Number(diastolic) * 10); }
        const wrongUnit = /^\s*kpa\b/.test(tail);
        if (wrongUnit) { systolic = ''; diastolic = ''; }
        const bpIssues = [...numericIssues, ...extra, ...(short ? ['Kısa tansiyon ifadesi mmHg değerine çevrildi; doğrulayın.'] : []), ...(wrongUnit ? ['Desteklenmeyen tansiyon birimi; mmHg değerini elle girin.'] : [])];
        add('systolic_bp', systolic, source, bpIssues); add('diastolic_bp', diastolic, source, bpIssues);
      };
      for (const match of pressureText.matchAll(bp)) addPressure(asNumber(match[1]), asNumber(match[2]), pressureText.slice(match.index! + match[0].length), []);
      if (!bloodPressure) {
        const bare = new RegExp(`\\b${bpLabel}((?:\\d+|${WORD})(?:\\s+(?:\\d+|${WORD}))+)(?![\\w])`, 'g');
        for (const match of pressureText.matchAll(bare)) {
          const pair = correction ? null : unseparatedPressure(match[1]);
          if (pair) addPressure(String(pair[0]), String(pair[1]), pressureText.slice(match.index! + match[0].length), ['Tansiyon ayırıcı olmadan söylendi; büyük/küçük değeri doğrulayın.']);
        }
      }
      if (!bloodPressure && /\b(?:tansiyon|kan basinci)\b/.test(text) && !new RegExp(`\\btansiyon(?:u)?\\s+${POLARITY}\\b`).test(text)) add('systolic_bp', '', source, ['Tam tansiyon değeri belirlenemedi.']);
      const patterns: Array<[VoiceField, string]> = [
        ['systolic_bp', 'sistolik(?: tansiyon)?'], ['diastolic_bp', 'diyastolik(?: tansiyon)?'],
        ['heart_rate', 'nab(?:iz|zi)|kalp hizi|kalp atimi|pulse'], ['respiratory_rate', 'solunum(?: sayisi| hizi)?'],
        ['temperature', 'ates(?:i)?|vucut sicakligi|vucut isisi'], ['spo2', 'spo2|spo₂|saturasyon(?:u)?|oksijen saturasyon(?:u)?|oksijen sat(?:urasyon)?'],
        ['height_cm', 'boy(?:u)?'], ['weight_kg', 'kilo(?:su)?|agirlik(?:i)?'],
        ['glucose_mg_dl', 'kan sekeri|aclik (?:kan )?sekeri|tokluk (?:kan )?sekeri|seker(?:i)?(?!\\s+hasta)|glukoz(?:u)?|kan glukozu'],
      ];
      for (const [field, label] of patterns) {
        const expression = new RegExp(`\\b(?:${label})\\s*[:=]?\\s*(?:(?:yaklasik|sanirim|galiba)\\s*)?(?:dakikada\\s*)?(?:(?:yuzde|%)\\s*)?(${NUMBER})(?![\\d])`, 'g');
        let matched = false;
        for (const match of text.matchAll(expression)) {
          matched = true;
          let value = asNumber(match[1]);
          let tail = text.slice(match.index! + match[0].length);
          const extra: string[] = [];
          // "Boy bir yetmiş beş" / "bir metre yetmiş beş" / "1 75" → 175 cm.
          const meters = field === 'height_cm' && !correction ? (normalize(match[1]).match(/^(?:bir|1)\s+(.+)$/) ?? (/^(?:bir|1)$/.test(match[1]) ? tail.match(new RegExp(`^\\s*(?:metre\\s+)?(${INTEGER})`)) : null)) : null;
          if (meters) {
            const centimeters = turkishNumber(meters[1]);
            if (centimeters !== null && Number.isInteger(centimeters) && centimeters < 100) {
              value = String(100 + centimeters); extra.push('Metre ifadesi santimetreye çevrildi; doğrulayın.');
              if (meters.index === 0 && meters.input === tail) tail = tail.slice(meters[0].length);
            }
          }
          const unsupported = /^\s*(?:mmol|fahrenheit|pound|lb\b|inch|inc\b|feet|ft\b|kpa|hz\b)/.test(tail) || (field === 'temperature' && /^\s*f\b/.test(tail));
          const incomplete = !extra.length && /[a-z]$/.test(match[1]) && /^[a-z]/.test(tail);
          if (field === 'height_cm' && !extra.length && /^\s*(?:metre|m\b)/.test(tail) && Number(value) < 3) value = String(Number(value) * 100);
          add(field, unsupported || incomplete ? '' : value, source, [...numericIssues, ...extra, ...(unsupported ? ['Desteklenmeyen birim; form biriminde değeri elle girin.'] : []), ...(incomplete ? ['Sayı ifadesi tamamlanamadı; değeri elle girin.'] : [])]);
        }
        // "Ateşi yok", "ateşi olmadı" are symptom statements (kept below as text), not missing measurements.
        const statement = new RegExp(`\\b(?:${label})\\s+${POLARITY}\\b`).test(text);
        if (!matched && !statement && new RegExp(`\\b(?:${label})(?=\\s|[:=%]|$)`).test(text)) add(field, '', source, [...numericIssues, 'Sayısal değer belirlenemedi.']);
      }
    }
    // Explicit section markers can occur several times in one utterance.
    const markers = [...text.matchAll(/\b(sikayet(?:i|ler(?:i)?)?|semptomlar|ozgecmis|anamnez|aile oykusu|ilaclar(?:i)?|kullandigi ilaclar|fizik muayene|muayenede|ek klinik not)\b\s*:?\s*/g)];
    const textStart = found.length;
    if (markers.length) {
      for (let index = 0; index < markers.length; index++) {
        const marker = markers[index];
        const field: VoiceField = /ilac/.test(marker[1]) ? 'medications' : /muayene|not/.test(marker[1]) ? 'notes' : /sikayet|semptom/.test(marker[1]) ? 'complaints' : 'history';
        const value = source.slice(marker.index! + marker[0].length, markers[index + 1]?.index ?? source.length).trim();
        section = { field, sentence: clause.sentence };
        if (value) add(field, value, source, issues);
      }
    } else if (/\b(?:sigara|alkol)\b/.test(text)) add('history', source, source, issues);
    else if (/\b(?:kullaniyor|kullanmakta|kullaniyormus|kullandigi|kullanir|ilac(?:i|lari)?)\b|\b\d+\s*(?:mg|mcg)\b|\b(?:miligram|mikrogram|tablet)\b(?!\s+desilitre)/.test(text) && found.length === start) add('medications', source, source, issues);
    else if (new RegExp(`\\b(?:oykusu|hipertansiyon(?:u)?|diyabet(?:i)?|seker hastal\\w*|seker hastasi|alerji(?:si)?|ameliyat\\w*|bobrek tasi|annesi|babasi|tansiyon(?:u)?\\s+${POLARITY})\\b`).test(text)) add('history', source, source, issues);
    else if (/\b(?:mukoza(?:si)?|turgor(?:u)?|ral(?:ler)?|ronkus|odem(?:i)?|batin|bilinc(?:i)?|oryante|koopere|hassasiyet|tasikardik)\b/.test(text)) add('notes', source, source, issues);
    else if (new RegExp(`\\b(?:kusma\\w*|kustu\\w*|bulanti\\w*|oksur\\w*|halsiz\\w*|agiz kurulugu|agri\\w*|bas donmesi\\w*|ishal\\w*|idrar miktarinda azalma|nefes darlig\\w*|nefes darlik\\w*|carpinti\\w*|titreme\\w*|kabiz\\w*|yorgun\\w*|istahsiz\\w*|ates(?:i|im)?\\s+${POLARITY}|atesl\\w*)`).test(text)) add('complaints', source, source, issues);
    // A comma-separated list continues the section named earlier in the same sentence.
    else if (section && found.length === start) add(section.field, source, source, issues);
    if (found.length > textStart && !markers.length && section && found[found.length - 1].field !== section.field) section = null;
    if (found.length === start) unmapped.push(source);
  }
  const candidates: VoiceCandidate[] = [];
  for (const field of Object.keys(VOICE_LABELS) as VoiceField[]) {
    const matches = found.filter((item) => item.field === field);
    if (!matches.length) continue;
    const alternatives = [...new Set(matches.map((item) => item.value).filter(Boolean))];
    const issues = [...new Set(matches.flatMap((item) => item.issues))];
    const conflict = !isVoiceTextField(field) && alternatives.length > 1;
    if (conflict) issues.push('Çelişkili değerler var; doğru değeri elle girin.');
    if (isVoiceTextField(field)) {
      const polarity = new Map<string, Set<string>>();
      for (const value of alternatives) {
        const match = normalize(value).match(new RegExp(`^(.*?)\\s+(${POLARITY})$`));
        if (!match) continue;
        const signs = polarity.get(match[1]) ?? new Set<string>();
        signs.add(/^(?:yok|olma|degil|cikma|yukselme)/.test(match[2]) ? 'negative' : 'positive'); polarity.set(match[1], signs);
      }
      if ([...polarity.values()].some((signs) => signs.size > 1)) issues.push('Çelişkili olumlu/olumsuz ifadeler var; metni kontrol edin.');
    }
    candidates.push({ field, value: conflict ? '' : isVoiceTextField(field) ? alternatives.join('\n') : alternatives[0] ?? '',
      source: [...new Set(matches.map((item) => item.source))], issues, alternatives });
  }
  return { candidates, unmapped };
}

export type VoiceChoice = { field: VoiceField; value: string; mode: 'append' | 'replace'; overwrite: boolean; reviewed: boolean };

/** Explicit approval + optimistic field comparison prevent silent overwrites. */
export function approvedVoicePatch(base: VoiceForm, current: VoiceForm, candidates: VoiceCandidate[], choices: VoiceChoice[], approved: boolean): Partial<VoiceForm> {
  if (!approved || !choices.length) throw new Error('Seçili alanları inceleyip onaylayın.');
  const patch: Partial<VoiceForm> = {};
  for (const choice of choices) {
    const candidate = candidates.find((item) => item.field === choice.field);
    if (!candidate) throw new Error('Taslak alanı geçersiz.');
    if (base[choice.field] !== current[choice.field]) throw new Error('Form alanı değişti; güncel değerleri incelemek için taslağı yenileyin.');
    const invalid = validateVoiceValue(choice.field, choice.value);
    if (invalid) throw new Error(`${VOICE_LABELS[choice.field]}: ${invalid}`);
    if (candidate.issues.length && !choice.reviewed) throw new Error('İşaretli belirsizlikleri ayrıca doğrulayın.');
    const previous = current[choice.field];
    const occupied = previous.trim() && !(choice.field === 'sex' && previous === 'unknown');
    const append = choice.mode === 'append' && isVoiceTextField(choice.field);
    if (occupied && !append && previous !== choice.value && !choice.overwrite) throw new Error('Mevcut değeri değiştirmek için alan bazında onay verin.');
    const value = choice.value.trim();
    patch[choice.field] = append && occupied && previous !== value ? [previous, value].join('\n') : isVoiceTextField(choice.field) ? value : value.replace(',', '.');
  }
  return patch;
}
