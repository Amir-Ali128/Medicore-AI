import { useState, type FormEvent } from 'react';

import SectionCard from '../components/ui/SectionCard';
import { evaluateClaudeAbnormalResults } from '../services/claudeReviewClient';
import {
  createManualRadiologyReport,
  uploadRadiologyReportPdf,
  type RadiologyReport,
} from '../services/radiologyClient';

const INPUT_CLASS =
  'mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950';

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

  const findings = Array.isArray(result?.findings) ? result?.findings : [];
  const criticalFindings = Array.isArray(result?.critical_findings)
    ? result?.critical_findings
    : [];

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">Radyoloji</p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">Görüntüleme raporları</h1>
      </header>

      <form onSubmit={submit}>
        <SectionCard title="Yeni radyoloji raporu" description="Metni yapıştır veya PDF yükle.">
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
              placeholder="Bulgular ve sonuç bölümünü buraya yapıştır..."
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

          {status ? <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">{status}</p> : null}
          {error ? <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">{error}</p> : null}

          <button
            type="submit"
            disabled={busy}
            className="mt-5 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-60"
          >
            {busy ? 'Kaydediliyor ve değerlendiriliyor…' : 'Kaydet ve tüm verilerle değerlendir'}
          </button>
        </SectionCard>
      </form>

      {result ? (
        <SectionCard title="Analiz sonucu" description={`${result.modality} · ${result.body_part}`}>
          <div className="space-y-4">
            <p className="text-sm leading-7 text-slate-700">{result.summary}</p>

            {criticalFindings.length > 0 ? (
              <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                <p className="font-semibold text-red-900">Kritik bulgular</p>
                <p className="mt-2 text-sm text-red-800">{criticalFindings.join(' · ')}</p>
              </div>
            ) : (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
                Kritik ifade saptanmadı. Hekim doğrulaması gereklidir.
              </div>
            )}

            <div>
              <h2 className="font-semibold text-slate-950">Bulgular</h2>
              <div className="mt-3 space-y-2">
                {findings.slice(0, 100).map((finding, index) => (
                  <div key={`${index}-${finding.text}`} className="rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-700">
                    {finding.text}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}
