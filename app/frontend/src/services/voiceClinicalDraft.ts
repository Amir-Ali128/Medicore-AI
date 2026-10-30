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
const NUMBER = `${INTEGER}(?:\\s*(?:[.,]|virgul|nokta)\\s*(?:\\d+|${WORD}(?:\\s+${WORD})?))?`;

/** Restricted Turkish number grammar: reject malformed sequences, never guess. */
export function turkishNumber(value: string): number | null {
  const normalized = normalize(value.trim());
  if (/^\d+(?:[.,]\d+)?$/.test(normalized)) return Number(normalized.replace(',', '.'));
  const pieces = normalized.split(/\s*(?:virgul|nokta|[.,])\s*/);
  if (pieces.length > 2) return null;
  function integer(text: string): number | null {
    const tokens = text.trim().split(/\s+/);
    if (tokens.some((token) => !(token in UNITS) && !(token in TENS) && token !== 'yuz' && token !== 'bin')) return null;
    let sum = 0, group = 0, previous = Infinity;
    for (const token of tokens) {
      if (token === 'bin') { if (sum || group > 9) return null; sum = (group || 1) * 1000; group = 0; previous = Infinity; }
      else if (token === 'yuz') { if (previous <= 100 && !(tokens.indexOf(token) === 1 && group > 0 && group < 10)) return null; group = (group || 1) * 100; previous = 100; }
      else {
        const value = UNITS[token] ?? TENS[token];
        if (value >= previous || (previous < 10 && value < 10)) return null;
        group += value; previous = value;
      }
    }
    return sum + group;
  }
  const whole = integer(pieces[0]);
  if (whole === null) return null;
  if (pieces.length === 1) return whole;
  const fraction = /^\d+$/.test(pieces[1]) ? pieces[1] : pieces[1].split(/\s+/).every((word) => word in UNITS)
    ? pieces[1].split(/\s+/).map((word) => UNITS[word]).join('') : String(integer(pieces[1]) ?? '');
  return /^\d+$/.test(fraction) ? Number(`${whole}.${fraction}`) : null;
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

/** Extraction only: preserve dictated text, explicit negation and source evidence. */
export function extractVoiceDraft(transcript: string): { candidates: VoiceCandidate[]; unmapped: string[] } {
  if (transcript.length > 12000) throw new Error('Transkripsiyon çok uzun; metni daha kısa bölümlere ayırın.');
  const found: Array<{ field: VoiceField; value: string; source: string; issues: string[] }> = [];
  const unmapped: string[] = [];
  function add(field: VoiceField, value: string, source: string, issues: string[] = []) {
    const invalid = value ? validateVoiceValue(field, value) : null;
    found.push({ field, value, source, issues: [...issues, ...(invalid ? [invalid] : []), ...(!value ? ['Değer belirlenemedi; elle doğrulayın.'] : [])] });
  }
  const clauses = transcript.split(/[;\n!?]+|\.(?!\d)|,(?!\d)/u).flatMap((source) => {
    const starts = [0, ...[...normalize(source).matchAll(/\b(?:sikayet(?:i|ler(?:i)?)?|semptomlar|ozgecmis|anamnez|aile oykusu|ilaclar(?:i)?|kullandigi ilaclar|fizik muayene|muayenede|ek klinik not|vital bulgular)\b/g)].map((match) => match.index!).filter((index) => index > 0)];
    return starts.map((start, index) => source.slice(start, starts[index + 1] ?? source.length).trim()).filter(Boolean);
  });
  let familyContext = false;
  for (const source of clauses) {
    const text = normalize(source);
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
      const bp = new RegExp(`\\b(?:tansiyon(?:u)?|kan basinci|ta)\\s*[:=]?\\s*(?:(?:yaklasik|sanirim|galiba)\\s*)?(${NUMBER})\\s*(?:/|bolu|uzeri)\\s*(${NUMBER})`, 'g');
      let bloodPressure = false;
      for (const match of text.matchAll(bp)) {
        bloodPressure = true;
        let systolic = asNumber(match[1]), diastolic = asNumber(match[2]);
        const short = systolic && diastolic && Number(systolic) <= 30 && Number(diastolic) <= 20;
        if (short) { systolic = String(Number(systolic) * 10); diastolic = String(Number(diastolic) * 10); }
        const wrongUnit = /^\s*kpa\b/.test(text.slice(match.index! + match[0].length));
        if (wrongUnit) { systolic = ''; diastolic = ''; }
        const bpIssues = [...numericIssues, ...(short ? ['Kısa tansiyon ifadesi mmHg değerine çevrildi; doğrulayın.'] : []), ...(wrongUnit ? ['Desteklenmeyen tansiyon birimi; mmHg değerini elle girin.'] : [])];
        add('systolic_bp', systolic, source, bpIssues); add('diastolic_bp', diastolic, source, bpIssues);
      }
      if (!bloodPressure && /\b(?:tansiyon|kan basinci)\b/.test(text)) add('systolic_bp', '', source, ['Tam tansiyon değeri belirlenemedi.']);
      const patterns: Array<[VoiceField, string]> = [
        ['systolic_bp', 'sistolik(?: tansiyon)?'], ['diastolic_bp', 'diyastolik(?: tansiyon)?'],
        ['heart_rate', 'nab(?:iz|zi)|kalp hizi|pulse'], ['respiratory_rate', 'solunum(?: sayisi| hizi)?'],
        ['temperature', 'ates(?:i)?|vucut sicakligi'], ['spo2', 'spo2|spo₂|saturasyon(?:u)?|oksijen saturasyon(?:u)?|oksijen sat(?:urasyon)?'],
        ['height_cm', 'boy(?:u)?'], ['weight_kg', 'kilo(?:su)?|agirlik(?:i)?'], ['glucose_mg_dl', 'kan sekeri|glukoz'],
      ];
      for (const [field, label] of patterns) {
        const expression = new RegExp(`\\b(?:${label})\\s*[:=]?\\s*(?:(?:yaklasik|sanirim|galiba)\\s*)?(?:(?:yuzde|%)\\s*)?(${NUMBER})(?![\\d])`, 'g');
        let matched = false;
        for (const match of text.matchAll(expression)) {
          matched = true;
          let value = asNumber(match[1]);
          const tail = text.slice(match.index! + match[0].length);
          const unsupported = /^\s*(?:mmol|fahrenheit|pound|lb\b|inch|inc\b|feet|ft\b|kpa|hz\b)/.test(tail) || (field === 'temperature' && /^\s*f\b/.test(tail));
          const incomplete = /[a-z]$/.test(match[1]) && /^[a-z]/.test(tail);
          if (field === 'height_cm' && /^\s*(?:metre|m\b)/.test(tail) && Number(value) < 3) value = String(Number(value) * 100);
          add(field, unsupported || incomplete ? '' : value, source, [...numericIssues, ...(unsupported ? ['Desteklenmeyen birim; form biriminde değeri elle girin.'] : []), ...(incomplete ? ['Sayı ifadesi tamamlanamadı; değeri elle girin.'] : [])]);
        }
        if (!matched && new RegExp(`\\b(?:${label})(?=\\s|[:=%]|$)`).test(text)) add(field, '', source, [...numericIssues, 'Sayısal değer belirlenemedi.']);
      }
    }
    // Explicit section markers can occur several times in one utterance.
    const markers = [...text.matchAll(/\b(sikayet(?:i|ler(?:i)?)?|semptomlar|ozgecmis|anamnez|aile oykusu|ilaclar(?:i)?|kullandigi ilaclar|fizik muayene|muayenede|ek klinik not)\s*:?\s*/g)];
    if (markers.length) {
      for (let index = 0; index < markers.length; index++) {
        const marker = markers[index];
        const field: VoiceField = /ilac/.test(marker[1]) ? 'medications' : /muayene|not/.test(marker[1]) ? 'notes' : /sikayet|semptom/.test(marker[1]) ? 'complaints' : 'history';
        const value = source.slice(marker.index! + marker[0].length, markers[index + 1]?.index ?? source.length).trim();
        if (value) add(field, value, source, issues);
      }
    } else if (/\b(?:oykusu|hipertansiyon(?:u)?|diyabet(?:i)?|alerji(?:si)?|ameliyat|bobrek tasi|annesi|babasi)\b/.test(text)) add('history', source, source, issues);
    else if (/\b(?:mukoza(?:si)?|turgor(?:u)?|ral(?:ler)?|ronkus|odem(?:i)?|batin|bilinc(?:i)?|oryante|koopere|hassasiyet|tasikardik)\b/.test(text)) add('notes', source, source, issues);
    else if (/\b(?:kusma|bulanti|oksuruk|halsizlik|agiz kurulugu|agrisi|agri|bas donmesi|ishal|idrar miktarinda azalma|nefes darligi)\b/.test(text)) add('complaints', source, source, issues);
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
        const match = normalize(value).match(/^(.*?)\s+(var|yok|degil)$/);
        if (!match) continue;
        const signs = polarity.get(match[1]) ?? new Set<string>();
        signs.add(match[2] === 'var' ? 'positive' : 'negative'); polarity.set(match[1], signs);
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
