import { useMemo, useState, type FormEvent } from 'react';

import SectionCard from '../components/ui/SectionCard';
import {
  createManualRadiologyReport,
  uploadRadiologyReportPdf,
  type RadiologyFinding,
  type RadiologyReport,
} from '../services/radiologyClient';

const INPUT_CLASS =
  'mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950';

function fold(value: string) {
  return value
    .toLocaleLowerCase('tr-TR')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/ı/g, 'i');
}

function isTechnicalSummary(value: string) {
  const text = fold(value);
  return (
    text.includes('klinik bulgu cumlesi') ||
    text.includes('dikkat gerektiren bulgu') ||
    text.includes('dogrulanmis kritik uyari') ||
    text.includes('olcum ve')
  );
}

function isNegative(text: string) {
  const value = fold(text);
  return [
    'saptanmadi',
    'saptanmamistir',
    'izlenmedi',
    'izlenmemistir',
    'izlenmemektedir',
    'mevcut degildir',
    'bulgu yok',
    'lehine bulgu yok',
  ].some((term) => value.includes(term));
}

function isRecommendation(text: string) {
  const value = fold(text);
  return [
    'onerilir',
    'onerilmektedir',
    'korelasyon',
    'konsultasyon',
    'takip',
    'kontrol',
    'degerlendirme',
  ].some((term) => value.includes(term));
}

function normalizeSentence(text: string) {
  return text.trim().replace(/\s+/g, ' ').replace(/^[•\-–—\s]+/, '');
}

function sentenceKey(text: string) {
  return fold(text)
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\b(yaklasik|mevcuttur|izlenmektedir|gorulmektedir)\b/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function uniqueSentences(sentences: string[]) {
  const output: string[] = [];
  const keys: string[] = [];

  for (const raw of sentences) {
    const sentence = normalizeSentence(raw);
    if (sentence.length < 4 || isTechnicalSummary(sentence)) continue;
    const key = sentenceKey(sentence);
    if (!key) continue;

    const duplicate = keys.some(
      (existing) => existing === key || existing.includes(key) || key.includes(existing),
    );
    if (!duplicate) {
      output.push(sentence.endsWith('.') ? sentence : `${sentence}.`);
      keys.push(key);
    }
  }

  return output;
}

function splitImpression(impression: string | null | undefined) {
  if (!impression || isTechnicalSummary(impression)) return [];
  return impression
    .split(/(?<=[.!?])\s+|\n+/)
    .map(normalizeSentence)
    .filter(Boolean);
}

function importantNegative(findings: RadiologyFinding[]) {
  const importantTerms = [
    'kanama',
    'enfarkt',
    'iskemi',
    'kitle etkisi',
    'orta hat sifti',
    'pnomotoraks',
    'pulmoner emboli',
    'serbest hava',
    'obstruksiyon',
    'metastaz',
  ];

  return findings
    .filter((finding) => isNegative(finding.text))
    .filter((finding) => {
      const text = fold(finding.text);
      return importantTerms.some((term) => text.includes(term));
    })
    .map((finding) => finding.text)
    .slice(0, 2);
}

function buildRadiologySummary(report: RadiologyReport | null) {
  if (!report) return '';

  const findings = Array.isArray(report.findings) ? report.findings : [];
  const critical = findings
    .filter((finding) => finding.is_critical && !isNegative(finding.text))
    .map((finding) => finding.text);
  const abnormal = findings
    .filter(
      (finding) =>
        !finding.is_critical &&
        !isNegative(finding.text) &&
        !isRecommendation(finding.text) &&
        finding.classification === 'abnormal',
    )
    .map((finding) => finding.text);
  const recommendations = findings
    .filter((finding) => isRecommendation(finding.text))
    .map((finding) => finding.text);

  const candidates = uniqueSentences([
    ...critical,
    ...abnormal,
    ...splitImpression(report.impression),
    ...importantNegative(findings),
    ...recommendations.slice(0, 1),
  ]);

  if (candidates.length > 0) return candidates.slice(0, 6).join(' ');

  const fallback = report.impression?.trim() || report.summary?.trim() || '';
  return isTechnicalSummary(fallback) ? '' : fallback;
}

function reportUrgency(report: RadiologyReport | null) {
  if (!report) return 'RUTİN';
  if (Array.isArray(report.critical_findings) && report.critical_findings.length > 0) {
    return 'ACİL';
  }

  const findings = Array.isArray(report.findings) ? report.findings : [];
  const hasAbnormalFinding = findings.some(
    (finding) => finding.classification === 'abnormal' && !isNegative(finding.text),
  );

  return hasAbnormalFinding ? 'DİKKAT' : 'RUTİN';
}

export default function RadiologyWorkspacePage() {
  const [mode, setMode] = useState<'manual' | 'pdf'>('manual');
  const [reportText, setReportText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<RadiologyReport | null>(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setStatus('');

    try {
      const report =
        mode === 'manual'
          ? await createManualRadiologyReport({
              reportDate: new Date().toISOString().slice(0, 10),
              modality: null,
              bodyPart: null,
              reportText,
            })
          : file
            ? await uploadRadiologyReportPdf(file, {
                reportDate: new Date().toISOString().slice(0, 10),
                modality: null,
                bodyPart: null,
              })
            : (() => {
                throw new Error('Önce bir PDF dosyası seçmelisin.');
              })();

      setResult(report);
      setStatus('Rapor kaydedildi ve rapora özel klinik özet oluşturuldu.');
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : 'Radyoloji analizi başarısız.',
      );
    } finally {
      setBusy(false);
    }
  }

  const summary = useMemo(() => buildRadiologySummary(result), [result]);
  const urgency = reportUrgency(result);
  const urgencyClass =
    urgency === 'ACİL'
      ? 'border-red-300 bg-red-600 text-white'
      : urgency === 'DİKKAT'
        ? 'border-amber-300 bg-amber-100 text-amber-950'
        : 'border-emerald-300 bg-emerald-100 text-emerald-950';

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">Radyoloji</p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">Görüntüleme raporu özeti</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Yüklenen raporun önemli patolojilerini, kritik negatif bulgularını ve önerilerini kısa bir klinik özet halinde sunar.
        </p>
      </header>

      <form onSubmit={submit}>
        <SectionCard title="Yeni görüntüleme raporu" description="Metni yapıştır veya PDF yükle.">
          <div className="flex gap-2">
            <button type="button" onClick={() => setMode('manual')} className="rounded-lg border px-4 py-2 text-sm font-semibold">Rapor metni</button>
            <button type="button" onClick={() => setMode('pdf')} className="rounded-lg border px-4 py-2 text-sm font-semibold">PDF yükle</button>
          </div>

          {mode === 'manual' ? (
            <textarea required minLength={10} rows={14} value={reportText} onChange={(event) => setReportText(event.target.value)} className={`${INPUT_CLASS} mt-5 resize-y`} placeholder="Rapor metnini buraya yapıştır..." />
          ) : (
            <input required type="file" accept="application/pdf,.pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} className={`${INPUT_CLASS} mt-5`} />
          )}

          {status ? <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">{status}</p> : null}
          {error ? <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">{error}</p> : null}

          <button type="submit" disabled={busy} className="mt-5 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-60">
            {busy ? 'Rapor özetleniyor…' : 'Kaydet ve raporu özetle'}
          </button>
        </SectionCard>
      </form>

      {result ? (
        <SectionCard title="Rapor özeti" description={`${result.modality} · ${result.body_part}`}>
          <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className={`rounded-full border px-4 py-2 text-sm font-extrabold tracking-wide ${urgencyClass}`}>Klinik öncelik: {urgency}</span>
              <span className="text-xs text-slate-500">Hekim doğrulaması zorunludur.</span>
            </div>

            <section className="rounded-xl border border-blue-200 bg-blue-50 p-5">
              <h2 className="font-semibold text-blue-950">AI radyoloji özeti</h2>
              {summary ? (
                <p className="mt-3 text-sm leading-7 text-blue-950">{summary}</p>
              ) : (
                <p className="mt-3 text-sm leading-7 text-blue-900">Bu rapordan anlamlı bir klinik özet oluşturulamadı. Orijinal rapor hekim tarafından değerlendirilmelidir.</p>
              )}
              <p className="mt-4 text-xs text-blue-800">Bu özet yalnızca yüklenen rapor metnine dayanır; tanı veya tedavi kararı değildir.</p>
            </section>
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}
