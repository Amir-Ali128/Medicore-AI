import { useMemo, useState, type FormEvent } from 'react';

import SectionCard from '../components/ui/SectionCard';
import { evaluateClaudeAbnormalResults } from '../services/claudeReviewClient';
import {
  createManualRadiologyReport,
  uploadRadiologyReportPdf,
  type RadiologyFinding,
  type RadiologyMeasurement,
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

function normalizedWords(value: string) {
  return new Set(
    fold(value)
      .replace(/[^a-z0-9ğüşöçı]+/g, ' ')
      .split(/\s+/)
      .filter((word) => word.length > 3 && !['yaklasik', 'mevcuttur', 'izlenmektedir'].includes(word)),
  );
}

function isNegativeFinding(text: string) {
  const value = fold(text);
  return [
    'saptanmadi',
    'saptanmamistir',
    'saptanmamaktadir',
    'izlenmedi',
    'izlenmemistir',
    'izlenmemektedir',
    'gorulmedi',
    'gorulmemistir',
    'gorulmemektedir',
    'mevcut degildir',
    'mevcut degil',
    'bulgu yok',
    'patoloji yok',
    'negatif',
  ].some((term) => value.includes(term));
}

function isRecommendation(text: string) {
  const value = fold(text);
  return [
    'onerilir',
    'onerilmektedir',
    'konsultasyon',
    'takip',
    'kontrol',
    'acil degerlendirme',
  ].some((term) => value.includes(term));
}

function isClinicallyEquivalent(left: string, right: string) {
  const a = fold(left);
  const b = fold(right);
  const sameConcept =
    (/(hematom|hemoraji|kanama)/.test(a) && /(hematom|hemoraji|kanama)/.test(b)) ||
    (a.includes('orta hat sifti') && b.includes('orta hat sifti')) ||
    (a.includes('kitle etkisi') && b.includes('kitle etkisi'));
  if (!sameConcept) return false;

  const leftWords = normalizedWords(left);
  const rightWords = normalizedWords(right);
  const overlap = [...leftWords].filter((word) => rightWords.has(word)).length;
  return overlap >= 2 || (a.includes('frontal') && b.includes('frontal'));
}

function uniqueFindings(findings: RadiologyFinding[]) {
  const output: RadiologyFinding[] = [];
  for (const finding of findings) {
    const exactKey = fold(finding.text).replace(/[^a-z0-9]+/g, ' ').trim();
    if (!exactKey) continue;
    const duplicate = output.some(
      (existing) =>
        fold(existing.text).replace(/[^a-z0-9]+/g, ' ').trim() === exactKey ||
        isClinicallyEquivalent(existing.text, finding.text),
    );
    if (!duplicate) output.push(finding);
  }
  return output;
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

function MeasurementGroup({ measurements }: { measurements: RadiologyMeasurement[] }) {
  if (measurements.length === 0) return null;
  return (
    <section>
      <h2 className="font-semibold text-slate-950">Ölçümler</h2>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {measurements.map((measurement, index) => (
          <div key={`${measurement.value}-${measurement.unit}-${index}`} className="rounded-lg border border-cyan-200 bg-cyan-50 p-3">
            <p className="font-semibold text-cyan-950">{measurement.value} {measurement.unit}</p>
            <p className="mt-1 text-xs leading-5 text-slate-600">{measurement.context}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function clinicalSummary(
  critical: RadiologyFinding[],
  positive: RadiologyFinding[],
  recommendations: RadiologyFinding[],
  impression: string | null,
) {
  const priority = [...critical, ...positive].slice(0, 3).map((item) => item.text);
  const sentences = priority.length > 0 ? priority : impression ? [impression] : [];
  if (recommendations[0]) sentences.push(recommendations[0].text);
  return sentences.join(' ');
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

  const view = useMemo(() => {
    const findings = uniqueFindings(Array.isArray(result?.findings) ? result.findings : []);
    const recommendations = findings.filter((item) => isRecommendation(item.text));
    const negatives = findings.filter((item) => !isRecommendation(item.text) && isNegativeFinding(item.text));
    const critical = findings.filter(
      (item) => !isRecommendation(item.text) && !isNegativeFinding(item.text) && item.is_critical,
    );
    const positive = findings.filter(
      (item) =>
        !isRecommendation(item.text) &&
        !isNegativeFinding(item.text) &&
        !item.is_critical &&
        item.classification === 'abnormal',
    );
    const other = findings.filter(
      (item) =>
        !isRecommendation(item.text) &&
        !isNegativeFinding(item.text) &&
        !item.is_critical &&
        item.classification !== 'abnormal',
    );
    return { findings, recommendations, negatives, critical, positive, other };
  }, [result]);

  const criticalWarnings = Array.isArray(result?.critical_findings) ? result.critical_findings : [];
  const measurements = Array.isArray(result?.measurements) ? result.measurements : [];
  const urgency = criticalWarnings.length > 0 ? 'ACİL' : view.positive.length > 0 ? 'DİKKAT' : 'RUTİN';
  const urgencyClass =
    urgency === 'ACİL'
      ? 'border-red-300 bg-red-600 text-white'
      : urgency === 'DİKKAT'
        ? 'border-amber-300 bg-amber-100 text-amber-950'
        : 'border-emerald-300 bg-emerald-100 text-emerald-950';
  const summary = result
    ? clinicalSummary(view.critical, view.positive, view.recommendations, result.impression)
    : '';

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
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className={`rounded-full border px-4 py-2 text-sm font-extrabold tracking-wide ${urgencyClass}`}>
                Klinik öncelik: {urgency}
              </span>
              <span className="text-xs text-slate-500">Hekim doğrulaması zorunludur.</span>
            </div>

            {summary ? (
              <section className="rounded-xl border border-blue-200 bg-blue-50 p-5">
                <h2 className="font-semibold text-blue-950">AI klinik özeti</h2>
                <p className="mt-2 text-sm leading-7 text-blue-950">{summary}</p>
                <p className="mt-3 text-xs text-blue-800">Bu özet yalnızca rapor metninden otomatik oluşturulmuştur; tanı veya tedavi kararı değildir.</p>
              </section>
            ) : null}

            {criticalWarnings.length > 0 ? (
              <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                <p className="font-semibold text-red-900">Kritik uyarılar</p>
                <p className="mt-2 text-sm text-red-800">{criticalWarnings.join(' · ')}</p>
              </div>
            ) : (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">Kritik ifade saptanmadı. Hekim doğrulaması gereklidir.</div>
            )}

            <FindingGroup title="Kritik bulgular" findings={view.critical} tone="red" />
            <FindingGroup title="Diğer pozitif bulgular" findings={view.positive} tone="amber" />
            <FindingGroup title="Negatif bulgular" findings={view.negatives} tone="emerald" />
            <MeasurementGroup measurements={measurements} />
            <FindingGroup title="Diğer rapor bulguları" findings={view.other} tone="slate" />
            <FindingGroup title="Öneri / izlem" findings={view.recommendations} tone="slate" />

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
