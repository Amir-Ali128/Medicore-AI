import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react';

import {
  createManualRadiologyReport,
  deleteRadiologyReport,
  downloadRadiologyOriginalFile,
  isAnalyzableRadiologyReport,
  listPatientRadiologyReports,
  uploadRadiologyReportFile,
  type RadiologyReport,
} from '../services/radiologyClient';

const INPUT_CLASS =
  'block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-950 placeholder:text-slate-400';

type FileUploadResult = {
  fileName: string;
  analyzed?: boolean;
  error?: string;
};

function fileKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function formatDate(value: string | null) {
  if (!value) return 'Tarih yok';
  return new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium' }).format(new Date(value));
}

export default function RadiologyEvaluationPage() {
  const [mode, setMode] = useState<'manual' | 'file'>('manual');
  const [reportText, setReportText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [uploadResults, setUploadResults] = useState<FileUploadResult[]>([]);
  const [reports, setReports] = useState<RadiologyReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [openingId, setOpeningId] = useState<string | null>(null);

  async function loadReports() {
    const stored = await listPatientRadiologyReports(null, { includeUnanalyzed: true });
    setReports(
      [...stored].sort(
        (a, b) => Date.parse(b.created_at ?? '') - Date.parse(a.created_at ?? ''),
      ),
    );
  }

  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      try {
        setLoading(true);
        setError('');
        const stored = await listPatientRadiologyReports(null, { includeUnanalyzed: true });
        if (!cancelled) {
          setReports(
            [...stored].sort(
              (a, b) => Date.parse(b.created_at ?? '') - Date.parse(a.created_at ?? ''),
            ),
          );
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Radyoloji ve tetkik kayıtları yüklenemedi.',
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

  function addFiles(event: ChangeEvent<HTMLInputElement>) {
    const incoming = Array.from(event.target.files ?? []);
    setFiles((current) => {
      const existing = new Set(current.map(fileKey));
      return [...current, ...incoming.filter((file) => !existing.has(fileKey(file)))];
    });
    setUploadResults([]);
    setError('');
    setStatus('');
    event.target.value = '';
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setStatus('');
    setUploadResults([]);

    try {
      if (mode === 'manual') {
        if (reportText.trim().length < 10) {
          throw new Error('Rapor metni en az 10 karakter olmalıdır.');
        }

        await createManualRadiologyReport({
          reportDate: new Date().toISOString().slice(0, 10),
          modality: null,
          bodyPart: null,
          reportText,
        });
        setReportText('');
        setStatus('Rapor değerlendirildi ve aktif hastanın kaydına eklendi.');
      } else {
        if (files.length === 0) {
          throw new Error('Önce en az bir dosya seçmelisin.');
        }

        const results: FileUploadResult[] = [];
        const failed: File[] = [];

        for (let index = 0; index < files.length; index += 1) {
          const file = files[index];
          setProgress(`${index + 1}/${files.length} · ${file.name} yükleniyor`);

          try {
            const report = await uploadRadiologyReportFile(file, {
              reportDate: new Date().toISOString().slice(0, 10),
              modality: null,
              bodyPart: null,
            });
            results.push({
              fileName: file.name,
              analyzed: isAnalyzableRadiologyReport(report),
            });
          } catch (uploadError) {
            failed.push(file);
            results.push({
              fileName: file.name,
              error:
                uploadError instanceof Error
                  ? uploadError.message
                  : 'Dosya yüklenemedi.',
            });
          }
          setUploadResults([...results]);
        }

        setFiles(failed);
        const successful = results.filter((item) => !item.error).length;
        if (successful > 0) {
          setStatus(`${successful} dosya aktif hastanın kaydına eklendi.`);
        }
        if (failed.length > 0) {
          setError(`${failed.length} dosya yüklenemedi; listede kalanları tekrar deneyebilirsin.`);
        }
      }

      await loadReports();
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'Rapor veya dosya kaydedilemedi.',
      );
    } finally {
      setProgress('');
      setBusy(false);
    }
  }

  async function removeReport(report: RadiologyReport) {
    if (!window.confirm('Bu kayıt kalıcı olarak silinsin mi?')) return;

    try {
      setDeletingId(report.id);
      setError('');
      await deleteRadiologyReport(report.id);
      setReports((current) => current.filter((item) => item.id !== report.id));
      setStatus('Kayıt silindi.');
    } catch (deleteError) {
      setError(
        deleteError instanceof Error ? deleteError.message : 'Kayıt silinemedi.',
      );
    } finally {
      setDeletingId(null);
    }
  }

  async function openOriginalFile(report: RadiologyReport) {
    try {
      setOpeningId(report.id);
      setError('');
      const blob = await downloadRadiologyOriginalFile(report.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = report.file_name || 'dosya';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (openError) {
      setError(openError instanceof Error ? openError.message : 'Dosya açılamadı.');
    } finally {
      setOpeningId(null);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-950">
          Radyoloji ve Diğer Tetkik Raporları
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          Rapor metni girebilir veya bir ya da birden fazla dosya yükleyebilirsin.
        </p>
      </header>

      <form onSubmit={submit} className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setMode('manual')}
            className={`rounded-lg border px-4 py-2 text-sm font-semibold ${
              mode === 'manual'
                ? 'border-blue-300 bg-blue-50 text-blue-800'
                : 'border-slate-200 text-slate-600'
            }`}
          >
            Rapor metni
          </button>
          <button
            type="button"
            onClick={() => setMode('file')}
            className={`rounded-lg border px-4 py-2 text-sm font-semibold ${
              mode === 'file'
                ? 'border-blue-300 bg-blue-50 text-blue-800'
                : 'border-slate-200 text-slate-600'
            }`}
          >
            Dosya yükle
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
            placeholder="Rapor metnini buraya yapıştırın..."
          />
        ) : (
          <div className="mt-4 space-y-3">
            <input
              type="file"
              multiple
              onChange={addFiles}
              className="block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-700 file:px-4 file:py-2.5 file:text-sm file:font-semibold file:text-white hover:file:bg-blue-800"
            />
            <p className="text-xs leading-5 text-slate-500">
              Tüm dosya türleri seçilebilir. PDF ve metin tabanlı dosyalar uygun olduğunda otomatik değerlendirilir; görüntü, DICOM, DOCX ve diğer formatlar dosya olarak saklanır ve otomatik görüntü yorumu yapılmaz. Dosya başına sınır 15 MB'dır.
            </p>
            <p className="text-xs leading-5 text-amber-700">
              Yüklenen dosyalarda isim, soyisim, T.C. kimlik numarası veya benzeri doğrudan kişisel tanımlayıcılar bulunmamalıdır.
            </p>

            {files.length > 0 ? (
              <div className="space-y-2">
                {files.map((file) => (
                  <div key={fileKey(file)} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-900">{file.name}</p>
                      <p className="text-xs text-slate-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setFiles((current) => current.filter((item) => fileKey(item) !== fileKey(file)))}
                      disabled={busy}
                      className="ml-3 text-xs font-semibold text-red-600 disabled:opacity-50"
                    >
                      Kaldır
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        )}

        <button
          type="submit"
          disabled={busy || (mode === 'file' && files.length === 0)}
          className="mt-4 w-full rounded-lg bg-blue-700 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {busy
            ? progress || 'Kaydediliyor…'
            : mode === 'manual'
              ? 'Değerlendir ve kaydet'
              : 'Dosyaları yükle ve kaydet'}
        </button>
      </form>

      {uploadResults.length > 0 ? (
        <div className="space-y-2">
          {uploadResults.map((item) => (
            <div
              key={item.fileName}
              className={`rounded-lg border px-4 py-3 text-sm ${
                item.error
                  ? 'border-red-200 bg-red-50 text-red-800'
                  : 'border-emerald-200 bg-emerald-50 text-emerald-800'
              }`}
            >
              <strong>{item.fileName}</strong>{' '}
              {item.error
                ? `— ${item.error}`
                : item.analyzed
                  ? '— değerlendirildi ve kaydedildi'
                  : '— dosya olarak kaydedildi (otomatik analiz yok)'}
            </div>
          ))}
        </div>
      ) : null}

      {status ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">{status}</div>
      ) : null}
      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>
      ) : null}

      {!loading && reports.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-slate-950">Kaydedilen rapor ve dosyalar</h2>
          {reports.map((report) => {
            const analyzable = isAnalyzableRadiologyReport(report);
            return (
              <article key={report.id} className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-slate-900">
                      {report.file_name || 'Rapor metni'}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {formatDate(report.report_date || report.created_at)} · {analyzable ? 'Değerlendirildi' : 'Dosya kaydı'}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{report.summary}</p>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    {report.file_name && report.metadata_json.original_file_stored === true ? (
                      <button
                        type="button"
                        onClick={() => void openOriginalFile(report)}
                        disabled={openingId === report.id}
                        className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-50"
                      >
                        {openingId === report.id ? 'Açılıyor…' : 'Dosyayı aç'}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => void removeReport(report)}
                      disabled={deletingId === report.id}
                      className="rounded-lg border border-red-200 px-3 py-2 text-xs font-semibold text-red-700 disabled:opacity-50"
                    >
                      {deletingId === report.id ? 'Siliniyor…' : 'Sil'}
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </section>
      ) : null}
    </div>
  );
}
