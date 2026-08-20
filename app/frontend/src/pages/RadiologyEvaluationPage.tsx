import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

import {
  createManualRadiologyReport,
  deleteRadiologyReport,
  listPatientRadiologyReports,
  uploadRadiologyReportPdf,
  type RadiologyReport,
} from '../services/radiologyClient';

const INPUT_CLASS =
  'block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-950 placeholder:text-slate-400';

type PdfUploadResult = {
  fileName: string;
  error?: string;
};

function fileKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

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

  const abnormal = report.findings
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
  const [pdfFiles, setPdfFiles] = useState<File[]>([]);
  const [pdfUploadResults, setPdfUploadResults] = useState<PdfUploadResult[]>([]);
  const [uploadProgress, setUploadProgress] = useState('');
  const [reports, setReports] = useState<RadiologyReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [deletingReportId, setDeletingReportId] = useState<string | null>(null);
  const [deletingAll, setDeletingAll] = useState(false);
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

  function addPdfFiles(event: ChangeEvent<HTMLInputElement>) {
    const incoming = Array.from(event.target.files ?? []).filter((file) =>
      file.name.toLowerCase().endsWith('.pdf'),
    );

    setPdfFiles((current) => {
      const existing = new Set(current.map(fileKey));
      return [...current, ...incoming.filter((file) => !existing.has(fileKey(file)))];
    });
    setPdfUploadResults([]);
    setError('');
    setStatus('');
    event.target.value = '';
  }

  function removePdfFile(file: File) {
    setPdfFiles((current) =>
      current.filter((item) => fileKey(item) !== fileKey(file)),
    );
    setPdfUploadResults([]);
    setError('');
  }

  async function submit(event: FormEvent) {
    event.preventDefault();

    try {
      setBusy(true);
      setError('');
      setStatus('');
      setPdfUploadResults([]);

      if (mode === 'manual') {
        if (reportText.trim().length < 10) {
          throw new Error('Radyoloji rapor metni en az 10 karakter olmalıdır.');
        }

        await createManualRadiologyReport({
          reportDate: new Date().toISOString().slice(0, 10),
          modality: null,
          bodyPart: null,
          reportText,
        });
        setReportText('');
        setStatus('Radyoloji raporu değerlendirildi ve kaydedildi.');
      } else {
        if (pdfFiles.length === 0) {
          throw new Error('Önce en az bir radyoloji PDF dosyası seçmelisin.');
        }

        const results: PdfUploadResult[] = [];
        const failedFiles: File[] = [];
        let successCount = 0;

        for (let index = 0; index < pdfFiles.length; index += 1) {
          const file = pdfFiles[index];
          setUploadProgress(`${index + 1}/${pdfFiles.length} · ${file.name} işleniyor`);

          try {
            await uploadRadiologyReportPdf(file, {
              reportDate: new Date().toISOString().slice(0, 10),
              modality: null,
              bodyPart: null,
            });
            successCount += 1;
            results.push({ fileName: file.name });
          } catch (uploadError) {
            failedFiles.push(file);
            results.push({
              fileName: file.name,
              error:
                uploadError instanceof Error
                  ? uploadError.message
                  : 'Radyoloji PDF’i işlenemedi.',
            });
          }

          setPdfUploadResults([...results]);
        }

        setPdfFiles(failedFiles);
        if (successCount > 0) {
          setStatus(`${successCount} radyoloji PDF’i değerlendirildi ve kaydedildi.`);
        }
        if (failedFiles.length > 0) {
          setError(`${failedFiles.length} PDF işlenemedi. Başarısız dosyaları tekrar deneyebilirsin.`);
        }
      }

      await loadReports();
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'Radyoloji raporu değerlendirilemedi.',
      );
    } finally {
      setUploadProgress('');
      setBusy(false);
    }
  }

  async function removeReport(report: RadiologyReport) {
    const approved = window.confirm(
      'Bu radyoloji raporunu kalıcı olarak silmek istediğine emin misin?',
    );
    if (!approved) return;

    try {
      setDeletingReportId(report.id);
      setError('');
      await deleteRadiologyReport(report.id);
      setReports((current) => current.filter((item) => item.id !== report.id));
      setStatus('Radyoloji raporu silindi.');
    } catch (deleteError) {
      setError(
        deleteError instanceof Error ? deleteError.message : 'Radyoloji raporu silinemedi.',
      );
    } finally {
      setDeletingReportId(null);
    }
  }

  async function removeAllReports() {
    const approved = window.confirm(
      'Bu hastaya ait tüm radyoloji raporlarını kalıcı olarak silmek istediğine emin misin?',
    );
    if (!approved) return;

    try {
      setDeletingAll(true);
      setError('');
      let deletedCount = 0;

      while (true) {
        const stored = await listPatientRadiologyReports();
        if (stored.length === 0) break;
        for (const report of stored) {
          await deleteRadiologyReport(report.id);
          deletedCount += 1;
        }
      }

      setReports([]);
      setStatus(`${deletedCount} radyoloji kaydı silindi.`);
    } catch (deleteError) {
      await loadReports().catch(() => undefined);
      setError(
        deleteError instanceof Error
          ? deleteError.message
          : 'Radyoloji kayıtları silinemedi.',
      );
    } finally {
      setDeletingAll(false);
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
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-950">Radyoloji Raporu</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          Rapor metnini yapıştırın veya PDF yükleyin. Rapor değerlendirilip hasta kaydına eklenir.
        </p>
      </header>

      <form
        onSubmit={submit}
        className="rounded-xl border border-slate-200 bg-white p-5"
      >
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setMode('manual')}
            className={`rounded-lg border px-4 py-2 text-sm font-semibold ${
              mode === 'manual'
                ? 'border-blue-300 bg-blue-50 text-blue-800'
                : 'border-slate-200 bg-white text-slate-600'
            }`}
          >
            Rapor metni
          </button>
          <button
            type="button"
            onClick={() => setMode('pdf')}
            className={`rounded-lg border px-4 py-2 text-sm font-semibold ${
              mode === 'pdf'
                ? 'border-blue-300 bg-blue-50 text-blue-800'
                : 'border-slate-200 bg-white text-slate-600'
            }`}
          >
            PDF yükle
          </button>
        </div>

        {mode === 'manual' ? (
          <textarea
            required
            minLength={10}
            rows={7}
            value={reportText}
            onChange={(event) => setReportText(event.target.value)}
            className={`${INPUT_CLASS} mt-4 resize-y`}
            placeholder="Radyoloji rapor metnini buraya yapıştırın..."
          />
        ) : (
          <div className="mt-4 space-y-3">
            <input
              type="file"
              accept="application/pdf,.pdf"
              multiple
              onChange={addPdfFiles}
              className="block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-700 file:px-4 file:py-2.5 file:text-sm file:font-semibold file:text-white hover:file:bg-blue-800"
            />

            {pdfFiles.length > 0 ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-slate-900">
                    Seçilen dosyalar ({pdfFiles.length})
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setPdfFiles([]);
                      setPdfUploadResults([]);
                    }}
                    disabled={busy}
                    className="text-xs font-semibold text-slate-500 hover:text-red-600 disabled:opacity-50"
                  >
                    Temizle
                  </button>
                </div>

                <div className="max-h-48 space-y-2 overflow-y-auto">
                  {pdfFiles.map((file) => (
                    <div
                      key={fileKey(file)}
                      className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-slate-900">
                          {file.name}
                        </p>
                        <p className="text-xs text-slate-500">
                          {(file.size / (1024 * 1024)).toFixed(2)} MB
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => removePdfFile(file)}
                        disabled={busy}
                        className="shrink-0 text-xs font-semibold text-red-600 disabled:opacity-50"
                      >
                        Kaldır
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        )}

        <button
          type="submit"
          disabled={busy || deletingAll || (mode === 'pdf' && pdfFiles.length === 0)}
          className="mt-4 w-full rounded-lg bg-blue-700 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {busy
            ? uploadProgress || 'Değerlendiriliyor…'
            : mode === 'pdf' && pdfFiles.length > 1
              ? `${pdfFiles.length} PDF’yi değerlendir ve kaydet`
              : 'Değerlendir ve kaydet'}
        </button>
      </form>

      {pdfUploadResults.length > 0 ? (
        <div className="space-y-2">
          {pdfUploadResults.map((item) => (
            <div
              key={item.fileName}
              className={`rounded-lg border px-4 py-3 text-sm ${
                item.error
                  ? 'border-red-200 bg-red-50 text-red-800'
                  : 'border-emerald-200 bg-emerald-50 text-emerald-800'
              }`}
            >
              <strong>{item.fileName}</strong>
              <span className="ml-2">
                {item.error ? `— ${item.error}` : '— kaydedildi'}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {status ? (
        <p className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
          {status}
        </p>
      ) : null}

      {error ? (
        <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </p>
      ) : null}

      {loading ? (
        <div className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-500">
          Kayıtlı raporlar yükleniyor…
        </div>
      ) : latestReport ? (
        <section className="rounded-xl border border-slate-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-950">Son radyoloji raporu</p>
              <p className="mt-1 text-xs text-slate-500">
                {latestReport.report_date || latestReport.created_at.slice(0, 10)}
              </p>
            </div>
            <span
              className={`rounded-full px-3 py-1.5 text-xs font-semibold ${urgencyClass(latestReport)}`}
            >
              {urgency(latestReport)}
            </span>
          </div>

          <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-slate-700">
            {reportSummary(latestReport)}
          </p>

          {abnormalFindings.length > 0 ? (
            <div className="mt-4 space-y-2">
              {abnormalFindings.slice(0, 5).map((finding, index) => (
                <div
                  key={`${finding.text}-${index}`}
                  className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950"
                >
                  {finding.text}
                </div>
              ))}
            </div>
          ) : null}

          <div className="mt-5 flex flex-wrap gap-2">
            <Link
              to="/combined-evaluation"
              className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800"
            >
              Birlikte değerlendir
            </Link>
            <button
              type="button"
              onClick={() => void removeReport(latestReport)}
              disabled={deletingReportId === latestReport.id || deletingAll}
              className="rounded-lg border border-red-200 px-4 py-2 text-sm font-semibold text-red-700 disabled:opacity-50"
            >
              {deletingReportId === latestReport.id ? 'Siliniyor…' : 'Sil'}
            </button>
          </div>
        </section>
      ) : null}

      {reports.length > 1 ? (
        <details className="rounded-xl border border-slate-200 bg-white p-5">
          <summary className="cursor-pointer text-sm font-semibold text-slate-900">
            Geçmiş radyoloji raporları ({reports.length - 1})
          </summary>
          <div className="mt-4 space-y-3">
            {reports.slice(1, 9).map((report) => (
              <article key={report.id} className="rounded-lg bg-slate-50 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">
                      {report.modality} · {report.body_part}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {report.report_date || report.created_at.slice(0, 10)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void removeReport(report)}
                    disabled={deletingReportId === report.id || deletingAll}
                    className="text-xs font-semibold text-red-600 disabled:opacity-50"
                  >
                    {deletingReportId === report.id ? 'Siliniyor…' : 'Sil'}
                  </button>
                </div>
                <p className="mt-3 line-clamp-3 text-sm leading-6 text-slate-600">
                  {reportSummary(report)}
                </p>
              </article>
            ))}

            <button
              type="button"
              onClick={() => void removeAllReports()}
              disabled={deletingAll}
              className="text-xs font-semibold text-red-700 disabled:opacity-50"
            >
              {deletingAll ? 'Tümü siliniyor…' : 'Tüm radyoloji geçmişini sil'}
            </button>
          </div>
        </details>
      ) : null}

      <p className="text-xs leading-6 text-slate-500">
        Radyoloji çıktıları karar destek amaçlıdır; hekim değerlendirmesinin yerine geçmez.
      </p>
    </div>
  );
}
