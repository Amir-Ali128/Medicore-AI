import { useState, type FormEvent } from 'react';

import SectionCard from '../components/ui/SectionCard';
import {
  createManualRadiologyReport,
  uploadRadiologyReportPdf,
  type RadiologyReport,
} from '../services/radiologyClient';

const INPUT_CLASS =
  'mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950';

function reportSummary(report: RadiologyReport | null) {
  if (!report) return '';
  return report.summary?.trim() || report.impression?.trim() || '';
}

function reportUrgency(report: RadiologyReport | null) {
  if (!report) return 'RUTİN';
  if (Array.isArray(report.critical_findings) && report.critical_findings.length > 0) {
    return 'ACİL';
  }

  const hasAbnormalFinding = Array.isArray(report.findings)
    ? report.findings.some((finding) => finding.classification === 'abnormal')
    : false;

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
      setStatus('Rapor kaydedildi ve yalnızca bu rapora bağlı AI özeti oluşturuldu.');
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : 'Radyoloji analizi başarısız.',
      );
    } finally {
      setBusy(false);
    }
  }

  const summary = reportSummary(result);
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
          Yüklenen görüntüleme raporunu analiz eder ve yalnızca o rapora bağlı kısa bir klinik özet oluşturur.
        </p>
      </header>

      <form onSubmit={submit}>
        <SectionCard title="Yeni görüntüleme raporu" description="Metni yapıştır veya PDF yükle.">
          <div className="flex gap-2">
            <button type="button" onClick={() => setMode('manual')} className="rounded-lg border px-4 py-2 text-sm font-semibold">
              Rapor metni
            </button>
            <button type="button" onClick={() => setMode('pdf')} className="rounded-lg border px-4 py-2 text-sm font-semibold">
              PDF yükle
            </button>
          </div>

          {mode === 'manual' ? (
            <textarea
              required
              minLength={10}
              rows={14}
              value={reportText}
              onChange={(event) => setReportText(event.target.value)}
              className={`${INPUT_CLASS} mt-5 resize-y`}
              placeholder="Rapor metnini buraya yapıştır..."
            />
          ) : (
            <input
              required
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className={`${INPUT_CLASS} mt-5`}
            />
          )}

          {status ? (
            <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
              {status}
            </p>
          ) : null}
          {error ? (
            <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={busy}
            className="mt-5 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-60"
          >
            {busy ? 'Rapor özetleniyor…' : 'Kaydet ve raporu özetle'}
          </button>
        </SectionCard>
      </form>

      {result ? (
        <SectionCard title="Rapor özeti" description={`${result.modality} · ${result.body_part}`}>
          <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className={`rounded-full border px-4 py-2 text-sm font-extrabold tracking-wide ${urgencyClass}`}>
                Klinik öncelik: {urgency}
              </span>
              <span className="text-xs text-slate-500">Hekim doğrulaması zorunludur.</span>
            </div>

            <section className="rounded-xl border border-blue-200 bg-blue-50 p-5">
              <h2 className="font-semibold text-blue-950">AI radyoloji özeti</h2>
              {summary ? (
                <p className="mt-3 whitespace-pre-line text-sm leading-7 text-blue-950">{summary}</p>
              ) : (
                <p className="mt-3 text-sm leading-7 text-blue-900">
                  Bu rapor için özet oluşturulamadı.
                </p>
              )}
              <p className="mt-4 text-xs text-blue-800">
                Bu özet yalnızca yüklenen rapor metnine dayanır; laboratuvar sonuçları, klinik öykü veya diğer raporlar bu ekranda değerlendirmeye katılmaz.
              </p>
            </section>
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}
