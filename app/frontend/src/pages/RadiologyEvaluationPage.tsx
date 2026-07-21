import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

import SectionCard from '../components/ui/SectionCard';
import {
  createManualRadiologyReport,
  listPatientRadiologyReports,
  uploadRadiologyReportPdf,
  type RadiologyReport,
} from '../services/radiologyClient';

const INPUT_CLASS =
  'mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950';

function fold(value: string | null | undefined) {
  return (value ?? '')
    .toLocaleLowerCase('tr-TR')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/ı/g, 'i')
    .replace(/\s+/g, ' ')
    .trim();
}

function reportFingerprint(report: RadiologyReport) {
  const original = fold(report.original_text).replace(/[^a-z0-9]+/g, ' ').trim();
  return original || `${report.modality}:${report.body_part}:${fold(report.summary)}`;
}

function uniqueLatestReports(reports: RadiologyReport[]) {
  const seen = new Set<string>();
  return [...reports]
    .sort((left, right) => {
      const leftDate = Date.parse(left.created_at ?? left.report_date ?? '') || 0;
      const rightDate = Date.parse(right.created_at ?? right.report_date ?? '') || 0;
      return rightDate - leftDate;
    })
    .filter((report) => {
      const key = reportFingerprint(report) || report.id;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function reportSummary(report: RadiologyReport) {
  if (report.summary?.trim() && report.summary !== 'Rapor özeti oluşturulamadı.') {
    return report.summary.trim();
  }
  if (report.impression?.trim()) return report.impression.trim();

  const abnormal = (Array.isArray(report.findings) ? report.findings : [])
    .filter((finding) => finding.is_critical || finding.classification === 'abnormal')
    .map((finding) => finding.text.trim())
    .filter(Boolean);
  if (abnormal.length > 0) return [...new Set(abnormal)].slice(0, 6).join(' ');

  const conclusion = report.original_text.match(
    /(?:sonuç|sonuc|izlenim)\s*:\s*([\s\S]{1,1200})$/i,
  );
  return conclusion?.[1]?.replace(/\s+/g, ' ').trim() || report.original_text.slice(0, 1000);
}

function urgency(report: RadiologyReport) {
  if (report.critical_findings.length > 0) return 'ACİL İNCELEME';
  if (report.findings.some((finding) => finding.classification === 'abnormal')) {
    return 'ANORMAL BULGU';
  }
  return 'RUTİN';
}

function urgencyClass(report: RadiologyReport) {
  const value = urgency(report);
  if (value === 'ACİL İNCELEME') return 'bg-red-100 text-red-800';
  if (value === 'ANORMAL BULGU') return 'bg-amber-100 text-amber-900';
  return 'bg-emerald-100 text-emerald-800';
}

export default function RadiologyEvaluationPage() {
  const [mode, setMode] = useState<'manual' | 'pdf'>('manual');
  const [reportText, setReportText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [reports, setReports] = useState<RadiologyReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');

  async function loadReports() {
    const stored = await listPatientRadiologyReports();
    setReports(uniqueLatestReports(stored));
  }

  useEffect(() => {
    let cancelled = false;
    async function hydrate() {
      try {
        setLoading(true);
        setError('');
        const stored = uniqueLatestReports(await listPatientRadiologyReports());
        if (!cancelled) setReports(stored);
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Radyoloji kayıtları yüklenemedi.',
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void hydrate();
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      setBusy(true);
      setError('');
      setStatus('');

      if (mode === 'manual') {
        await createManualRadiologyReport({
          reportDate: new Date().toISOString().slice(0, 10),
          modality: null,
          bodyPart: null,
          reportText,
        });
      } else if (file) {
        await uploadRadiologyReportPdf(file, {
          reportDate: new Date().toISOString().slice(0, 10),
          modality: null,
          bodyPart: null,
        });
      } else {
        throw new Error('Önce bir radyoloji PDF dosyası seçmelisin.');
      }

      await loadReports();
      setReportText('');
      setFile(null);
      setStatus(
        'Radyoloji raporu ayrı olarak değerlendirildi ve hasta kaydına kalıcı biçimde eklendi.',
      );
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'Radyoloji raporu değerlendirilemedi.',
      );
    } finally {
      setBusy(false);
    }
  }

  const latestReport = reports[0] ?? null;
  const abnormalFindings = useMemo(
    () =>
      latestReport?.findings.filter(
        (finding) => finding.is_critical || finding.classification === 'abnormal',
      ) ?? [],
    [latestReport],
  );

  return (
    <div className="space-y-8">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-violet-700">
          Aşama 1 — Bağımsız değerlendirme
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">
          Radyoloji raporu değerlendirmesi
        </h1>
        <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-600">
          Radyoloji raporu bu ekranda kendi bulguları, ölçümleri ve sonuç bölümü üzerinden
          değerlendirilir ve saklanır. Klinik ve kan verileriyle birleşik değerlendirme ayrı
          ekranda yapılır.
        </p>
      </header>

      <form onSubmit={submit}>
        <SectionCard
          title="Radyoloji raporu ekle"
          description="Rapor metnini yapıştır veya metin tabanlı PDF yükle."
        >
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setMode('manual')}
              className={`rounded-lg border px-4 py-2 text-sm font-semibold ${
                mode === 'manual' ? 'border-violet-300 bg-violet-50 text-violet-800' : ''
              }`}
            >
              Rapor metni
            </button>
            <button
              type="button"
              onClick={() => setMode('pdf')}
              className={`rounded-lg border px-4 py-2 text-sm font-semibold ${
                mode === 'pdf' ? 'border-violet-300 bg-violet-50 text-violet-800' : ''
              }`}
            >
              PDF yükle
            </button>
          </div>

          {mode === 'manual' ? (
            <textarea
              required
              minLength={10}
              rows={12}
              value={reportText}
              onChange={(event) => setReportText(event.target.value)}
              className={`${INPUT_CLASS} mt-5 resize-y`}
              placeholder="Radyoloji rapor metnini buraya yapıştır..."
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
            className="mt-5 rounded-lg bg-violet-700 px-5 py-3 text-sm font-semibold text-white disabled:opacity-60"
          >
            {busy ? 'Rapor değerlendiriliyor ve kaydediliyor…' : 'Raporu değerlendir ve kaydet'}
          </button>
        </SectionCard>
      </form>

      {loading ? (
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
          Kayıtlı radyoloji raporları yükleniyor…
        </div>
      ) : latestReport ? (
        <SectionCard
          title="En güncel radyoloji değerlendirmesi"
          description={`${latestReport.modality} · ${latestReport.body_part}`}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className={`rounded-full px-3 py-1.5 text-xs font-semibold ${urgencyClass(latestReport)}`}>
              {urgency(latestReport)}
            </span>
            <span className="text-xs text-slate-500">
              {latestReport.report_date || latestReport.created_at.slice(0, 10)}
            </span>
          </div>

          <div className="mt-5 rounded-xl border border-violet-100 bg-violet-50 p-5">
            <h3 className="font-semibold text-violet-950">Rapor özeti</h3>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-8 text-violet-950">
              {reportSummary(latestReport)}
            </p>
          </div>

          <div className="mt-5 grid gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-2xl font-semibold text-slate-950">{latestReport.findings.length}</p>
              <p className="text-xs text-slate-500">Toplam bulgu</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-2xl font-semibold text-amber-700">{abnormalFindings.length}</p>
              <p className="text-xs text-slate-500">Anormal/kritik bulgu</p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-2xl font-semibold text-blue-700">{latestReport.measurements.length}</p>
              <p className="text-xs text-slate-500">Ölçüm</p>
            </div>
          </div>

          {abnormalFindings.length > 0 ? (
            <div className="mt-5 space-y-2">
              {abnormalFindings.slice(0, 8).map((finding, index) => (
                <div
                  key={`${finding.text}-${index}`}
                  className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-950"
                >
                  {finding.text}
                </div>
              ))}
            </div>
          ) : null}

          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to="/combined-evaluation"
              className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white"
            >
              Klinik + kan + radyolojiyi birlikte değerlendir
            </Link>
          </div>
        </SectionCard>
      ) : (
        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-600">
          Henüz kaydedilmiş radyoloji raporu bulunmuyor.
        </div>
      )}

      {reports.length > 1 ? (
        <SectionCard
          title="Radyoloji raporu geçmişi"
          description="Aynı hastaya ait benzersiz raporlar kalıcı kayıttan yüklenir."
        >
          <div className="grid gap-4 lg:grid-cols-2">
            {reports.slice(1, 9).map((report) => (
              <article key={report.id} className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-semibold text-slate-950">
                    {report.modality} · {report.body_part}
                  </p>
                  <span className="text-xs text-slate-500">
                    {report.report_date || report.created_at.slice(0, 10)}
                  </span>
                </div>
                <p className="mt-3 line-clamp-5 text-sm leading-6 text-slate-600">
                  {reportSummary(report)}
                </p>
              </article>
            ))}
          </div>
        </SectionCard>
      ) : null}

      <p className="text-xs leading-6 text-slate-500">
        Radyoloji çıktıları karar destek amaçlıdır; hekim tarafından doğrulanmadan tanı veya
        tedavi kararı olarak kullanılamaz.
      </p>
    </div>
  );
}
