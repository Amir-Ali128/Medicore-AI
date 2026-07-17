import { useState, type FormEvent } from 'react';

import SectionCard from '../components/ui/SectionCard';
import { evaluateClaudeAbnormalResults } from '../services/claudeReviewClient';
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

function isNegativeFinding(text: string) {
  const value = fold(text);
  return [
    'saptanmadi',
    'saptanmamistir',
    'izlenmedi',
    'izlenmemistir',
    'gorulmedi',
    'gorulmemistir',
    'mevcut degildir',
    'bulgu yok',
    'patoloji yok',
    'negatif',
  ].some((term) => value.includes(term));
}

function isRecommendation(text: string) {
  const value = fold(text);
  return ['onerilir', 'degerlendirme onerilir', 'konsultasyon', 'takip onerilir'].some((term) =>
    value.includes(term),
  );
}

function uniqueFindings(findings: RadiologyFinding[]) {
  const seen = new Set<string>();
  return findings.filter((finding) => {
    const key = fold(finding.text).replace(/[^a-z0-9]+/g, ' ').trim();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function FindingGroup({
  title,
  findings,
  tone,
}: {
  title: string;
  findings: RadiologyFinding[];
  tone: 'red' | 'amber' | 'emerald' | 'slate';
}) {
  if (findings.length === 0) return null;
  const classes = {
    red: 'border-red-200 bg-red-50 text-red-950',
    amber: 'border-amber-200 bg-amber-50 text-amber-950',
    emerald: 'border-emerald-200 bg-emerald-50 text-emerald-950',
    slate: 'border-slate-200 bg-slate-50 text-slate-800',
  }[tone];

  return (
    <section>
      <h2 className="font-semibold text-slate-950">{title}</h2>
      <div className="mt-3 space-y-2">
        {findings.map((finding, index) => (
          <div key={`${title}-${index}-${finding.text}`} className={`rounded-lg border p-3 text-sm ${classes}`}>
            {finding.text}
          </div>
        ))}
      </div>
    </section>
  );
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
      setStatus('Rapor kaydedildi ve analiz edildi.');

      const analysisRunId = localStorage.getItem('medicore:lastAnalysisRunId');
      if (analysisRunId) {
        try {
          await evaluateClaudeAbnormalResults(analysisRunId, 5);
          setStatus('Rapor kaydedildi ve tüm hasta verileriyle birlikte değerlendirildi.');
        } catch {
          setStatus('Rapor kaydedildi. Birleşik klinik değerlendirme şu anda tamamlanamadı.');
        }
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Radyoloji analizi başarısız.');
    } finally {
      setBusy(false);
    }
  }

  const findings = uniqueFindings(Array.isArray(result?.findings) ? result.findings : []);
  const criticalFindings = Array.isArray(result?.critical_findings) ? result.critical_findings : [];
  const recommendationFindings = findings.filter((item) => isRecommendation(item.text));
  const negativeFindings = findings.filter(
    (item) => !isRecommendation(item.text) && isNegativeFinding(item.text),
  );
  const criticalSentences = findings.filter(
    (item) => !isRecommendation(item.text) && !isNegativeFinding(item.text) && item.is_critical,
  );
  const positiveFindings = findings.filter(
    (item) =>
      !isRecommendation(item.text) &&
      !isNegativeFinding(item.text) &&
      !item.is_critical &&
      item.classification === 'abnormal',
  );
  const otherFindings = findings.filter(
    (item) =>
      !isRecommendation(item.text) &&
      !isNegativeFinding(item.text) &&
      !item.is_critical &&
      item.classification !== 'abnormal',
  );

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">Radyoloji</p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">Görüntüleme raporları</h1>
      </header>

      <form onSubmit={submit}>
        <SectionCard title="Yeni radyoloji raporu" description="Metni yapıştır veya PDF yükle.">
          <div className="flex gap-2">
            <button type="button" onClick={() => setMode('manual')} className="rounded-lg border px-4 py-2 text-sm font-semibold">Rapor metni</button>
            <button type="button" onClick={() => setMode('pdf')} className="rounded-lg border px-4 py-2 text-sm font-semibold">PDF yükle</button>
          </div>

          {mode === 'manual' ? (
            <textarea required minLength={10} rows={14} value={reportText} onChange={(event) => setReportText(event.target.value)} className={`${INPUT_CLASS} mt-5 resize-y`} placeholder="Bulgular ve sonuç bölümünü buraya yapıştır..." />
          ) : (
            <input required type="file" accept="application/pdf,.pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} className={`${INPUT_CLASS} mt-5`} />
          )}

          {status ? <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">{status}</p> : null}
          {error ? <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">{error}</p> : null}

          <button type="submit" disabled={busy} className="mt-5 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-60">
            {busy ? 'Kaydediliyor ve değerlendiriliyor…' : 'Kaydet ve tüm verilerle değerlendir'}
          </button>
        </SectionCard>
      </form>

      {result ? (
        <SectionCard title="Analiz sonucu" description={`${result.modality} · ${result.body_part}`}>
          <div className="space-y-5">
            <p className="text-sm leading-7 text-slate-700">{result.summary}</p>

            {criticalFindings.length > 0 ? (
              <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                <p className="font-semibold text-red-900">Kritik uyarılar</p>
                <p className="mt-2 text-sm text-red-800">{criticalFindings.join(' · ')}</p>
              </div>
            ) : (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">Kritik ifade saptanmadı. Hekim doğrulaması gereklidir.</div>
            )}

            <FindingGroup title="Kritik bulgular" findings={criticalSentences} tone="red" />
            <FindingGroup title="Diğer pozitif bulgular" findings={positiveFindings} tone="amber" />
            <FindingGroup title="Negatif bulgular" findings={negativeFindings} tone="emerald" />
            <FindingGroup title="Diğer rapor bulguları" findings={otherFindings} tone="slate" />
            <FindingGroup title="Öneri / izlem" findings={recommendationFindings} tone="slate" />

            {result.impression ? (
              <section className="rounded-lg border border-violet-200 bg-violet-50 p-4">
                <h2 className="font-semibold text-violet-950">Sonuç / izlenim</h2>
                <p className="mt-2 text-sm leading-6 text-violet-900">{result.impression}</p>
              </section>
            ) : null}
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}
