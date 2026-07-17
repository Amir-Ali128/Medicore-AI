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

function isNegativeFinding(text: string) {
  const value = fold(text);
  return [
    'saptanmadi', 'saptanmamistir', 'saptanmamaktadir',
    'izlenmedi', 'izlenmemistir', 'izlenmemektedir',
    'gorulmedi', 'gorulmemistir', 'gorulmemektedir',
    'mevcut degildir', 'mevcut degil', 'bulgu yok',
    'patoloji yok', 'negatif',
  ].some((term) => value.includes(term));
}

function isRecommendation(text: string) {
  const value = fold(text);
  return ['onerilir', 'onerilmektedir', 'konsultasyon', 'takip', 'kontrol', 'acil degerlendirme']
    .some((term) => value.includes(term));
}

function isPositiveClinicalFinding(text: string) {
  if (isNegativeFinding(text) || isRecommendation(text)) return false;
  const value = fold(text);
  return [
    'basili', 'basi', 'mukozal kalinlasma', 'kalinlasma', 'duvar kalinligi',
    'odem', 'hematom', 'hemoraji', 'kanama', 'sift', 'kitle etkisi',
    'efüzyon', 'efuzyon', 'konsolidasyon', 'infiltrasyon', 'atelektazi',
    'lezyon', 'nodul', 'dilatasyon', 'stenoz', 'koleksiyon', 'metastaz',
    'hipodens', 'hiperdens', 'kalkul', 'kolelitiazis', 'tas',
    'trombus', 'tromboz', 'kompresyon kaybi', 'akim izlenmemektedir',
    'kirlenme', 'periappendikuler', 'apandisit',
  ].some((term) => value.includes(term));
}

function isCriticalUltrasoundFinding(text: string) {
  if (isNegativeFinding(text)) return false;
  const value = fold(text);
  return [
    'akut derin ven trombozu',
    'derin ven trombozu',
    'dvt',
    'testis torsiyonu',
    'ektopik gebelik',
    'rüptüre ektopik',
    'rupture ektopik',
    'aort anevrizmasi rüptürü',
    'aort anevrizmasi rupturu',
    'tam venoz okluzyon',
  ].some((term) => value.includes(term));
}

function normalizedWords(value: string) {
  return new Set(
    fold(value)
      .replace(/[^a-z0-9]+/g, ' ')
      .split(/\s+/)
      .filter((word) => word.length > 3 && !['yaklasik', 'mevcuttur', 'izlenmektedir'].includes(word)),
  );
}

function isClinicallyEquivalent(left: string, right: string) {
  const a = fold(left);
  const b = fold(right);
  const sameConcept =
    (/(hematom|hemoraji|kanama)/.test(a) && /(hematom|hemoraji|kanama)/.test(b)) ||
    (/(nodul)/.test(a) && /(nodul)/.test(b)) ||
    (/(trombus|tromboz)/.test(a) && /(trombus|tromboz)/.test(b)) ||
    (/(kalkul|kolelitiazis|tas)/.test(a) && /(kalkul|kolelitiazis|tas)/.test(b)) ||
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

function inferDisplayBodyPart(report: RadiologyReport) {
  const text = fold(report.original_text ?? '');
  if (/alt ekstremite|femoral ven|popliteal ven|venoz doppler|derin ven trombozu/.test(text)) {
    return 'LOWER_EXTREMITY';
  }
  if (/tiroid/.test(text)) return 'NECK';
  if (/skrotal|testis/.test(text)) return 'SCROTUM';
  if (/obstetrik|gebelik|fetus|plasenta/.test(text)) return 'OBSTETRIC';
  return report.body_part;
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

function measurementLabel(measurement: RadiologyMeasurement) {
  const context = measurement.context ?? '';
  const unit = measurement.unit.replace(/\s+/g, '');
  const escapedUnit = unit.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const multiAxis = new RegExp(
    `(\\d+(?:[.,]\\d+)?)\\s*[x×*]\\s*(\\d+(?:[.,]\\d+)?)(?:\\s*[x×*]\\s*(\\d+(?:[.,]\\d+)?))?\\s*${escapedUnit}`,
    'i',
  ).exec(context);
  if (multiAxis) {
    const dimensions = [multiAxis[1], multiAxis[2], multiAxis[3]].filter(Boolean);
    return `${dimensions.join(' × ')} ${measurement.unit}`;
  }
  return `${measurement.value} ${measurement.unit}`;
}

function uniqueMeasurements(measurements: RadiologyMeasurement[]) {
  const output: RadiologyMeasurement[] = [];
  for (const measurement of measurements) {
    const label = measurementLabel(measurement);
    const duplicate = output.some((existing) => {
      if (measurementLabel(existing) !== label) return false;
      const a = normalizedWords(existing.context ?? '');
      const b = normalizedWords(measurement.context ?? '');
      return [...a].filter((word) => b.has(word)).length >= 2;
    });
    if (!duplicate) output.push(measurement);
  }
  return output;
}

function MeasurementGroup({ measurements }: { measurements: RadiologyMeasurement[] }) {
  const unique = uniqueMeasurements(measurements);
  if (unique.length === 0) return null;
  return (
    <section>
      <h2 className="font-semibold text-slate-950">Ölçümler</h2>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {unique.map((measurement, index) => (
          <div key={`${measurementLabel(measurement)}-${index}`} className="rounded-lg border border-cyan-200 bg-cyan-50 p-3">
            <p className="font-semibold text-cyan-950">{measurementLabel(measurement)}</p>
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
  const priority = [...critical, ...positive].slice(0, 4).map((item) => item.text);
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
      (item) =>
        !isRecommendation(item.text) &&
        !isNegativeFinding(item.text) &&
        (item.is_critical || isCriticalUltrasoundFinding(item.text)),
    );
    const positive = findings.filter(
      (item) =>
        !isRecommendation(item.text) &&
        !isNegativeFinding(item.text) &&
        !critical.includes(item) &&
        (item.classification === 'abnormal' || isPositiveClinicalFinding(item.text)),
    );
    const other = findings.filter(
      (item) =>
        !isRecommendation(item.text) &&
        !isNegativeFinding(item.text) &&
        !critical.includes(item) &&
        !positive.includes(item),
    );
    return { findings, recommendations, negatives, critical, positive, other };
  }, [result]);

  const backendWarnings = Array.isArray(result?.critical_findings) ? result.critical_findings : [];
  const derivedWarnings = view.critical
    .filter((item) => isCriticalUltrasoundFinding(item.text))
    .map(() => 'Akut derin ven trombozu');
  const criticalWarnings = [...new Set([...backendWarnings, ...derivedWarnings])];
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
  const displayBodyPart = result ? inferDisplayBodyPart(result) : '';

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
        <SectionCard title="Analiz sonucu" description={`${result.modality} · ${displayBodyPart}`}>
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
