import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react';

import {
  createManualRadiologyReport,
  deleteRadiologyReport,
  downloadRadiologyOriginalFile,
  isAnalyzableRadiologyReport,
  isVisualAiReview,
  listPatientRadiologyReports,
  uploadRadiologyImageReview,
  uploadRadiologyReportFile,
  type RadiologyImageModality,
  type RadiologyReport,
} from '../services/radiologyClient';

const INPUT_CLASS =
  'block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-950 placeholder:text-slate-400';

type FilePurpose = 'report' | 'xray' | 'ultrasound';

type FileUploadResult = {
  fileName: string;
  analyzed?: boolean;
  visualAi?: boolean;
  error?: string;
};

function fileKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function formatDate(value: string | null) {
  if (!value) return 'Tarih yok';
  return new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium' }).format(new Date(value));
}

function isSupportedVisualImage(file: File) {
  const mediaType = file.type.toLowerCase();
  const extension = file.name.toLowerCase().split('.').pop() ?? '';
  return (
    ['image/jpeg', 'image/png', 'image/webp'].includes(mediaType) ||
    ['jpg', 'jpeg', 'png', 'webp'].includes(extension)
  );
}

function purposeModality(purpose: FilePurpose): RadiologyImageModality | null {
  if (purpose === 'xray') return 'XRAY';
  if (purpose === 'ultrasound') return 'ULTRASOUND';
  return null;
}

export default function RadiologyEvaluationPage() {
  const [mode, setMode] = useState<'manual' | 'file'>('manual');
  const [filePurpose, setFilePurpose] = useState<FilePurpose>('report');
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
        const modality = purposeModality(filePurpose);

        for (let index = 0; index < files.length; index += 1) {
          const file = files[index];
          const wantsVisualAi = Boolean(modality) && isSupportedVisualImage(file);
          setProgress(
            `${index + 1}/${files.length} · ${file.name} ${wantsVisualAi ? 'AI ile inceleniyor' : 'yükleniyor'}`,
          );

          try {
            const report = wantsVisualAi && modality
              ? await uploadRadiologyImageReview(file, modality)
              : await uploadRadiologyReportFile(file, {
                  reportDate: new Date().toISOString().slice(0, 10),
                  modality,
                  bodyPart: null,
                });
            results.push({
              fileName: file.name,
              analyzed: isAnalyzableRadiologyReport(report),
              visualAi: isVisualAiReview(report),
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
          setError(`${failed.length} dosya işlenemedi; listede kalanları tekrar deneyebilirsin.`);
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
          Rapor metni, dosya veya şimdilik röntgen/ultrason görüntüsü ekleyebilirsin.
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
            Dosya / görüntü yükle
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
          <div className="mt-4 space-y-4">
            <label className="block max-w-sm text-sm font-medium text-slate-800">
              Yükleme türü
              <select
                value={filePurpose}
                onChange={(event) => setFilePurpose(event.target.value as FilePurpose)}
                className={`${INPUT_CLASS} mt-2`}
              >
                <option value="report">Rapor / diğer dosya</option>
                <option value="xray">Röntgen görüntüsü</option>
                <option value="ultrasound">Ultrason görüntüsü</option>
              </select>
            </label>

            <input
              type="file"
              multiple
              onChange={addFiles}
              className="block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-700 file:px-4 file:py-2.5 file:text-sm file:font-semibold file:text-white hover:file:bg-blue-800"
            />

            {filePurpose === 'report' ? (
              <p className="text-xs leading-5 text-slate-500">
                Tüm dosya türleri seçilebilir. PDF ve metin tabanlı dosyalar uygun olduğunda değerlendirilir; diğer formatlar arşivlenir. Dosya başına sınır 15 MB'dır.
              </p>
            ) : (
              <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 text-xs leading-5 text-violet-900">
                JPG, PNG veya WEBP görüntülerinde deneysel <strong>AI (DL/ML) ön değerlendirmesi</strong> çalışır. DICOM ve diğer formatlar aynı hastaya dosya olarak kaydedilir ancak şimdilik görüntü modeli tarafından yorumlanmaz. Bu çıktı tanı değildir ve hekim/radyolog doğrulaması gerektirir.
              </div>
            )}

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
              : filePurpose === 'report'
                ? 'Dosyaları yükle ve kaydet'
                : 'Görüntüleri değerlendir ve kaydet'}
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
                : item.visualAi
                  ? '— AI (DL/ML) ön değerlendirmesi yapıldı ve kaydedildi'
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
            const visualAi = isVisualAiReview(report);
            const limitations = Array.isArray(report.metadata_json.analysis_limitations)
              ? (report.metadata_json.analysis_limitations as string[])
              : [];
            return (
              <article key={report.id} className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate font-semibold text-slate-900">
                        {report.file_name || 'Rapor metni'}
                      </p>
                      {visualAi ? (
                        <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-800">
                          AI görüntü ön değerlendirmesi
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      {formatDate(report.report_date || report.created_at)} · {report.modality} · {analyzable ? 'Değerlendirildi' : 'Dosya kaydı'}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{report.summary}</p>

                    {visualAi && report.findings.length > 0 ? (
                      <div className="mt-3 rounded-lg bg-slate-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Görsel gözlemler</p>
                        <ul className="mt-2 space-y-1 text-sm leading-6 text-slate-700">
                          {report.findings.map((finding, index) => (
                            <li key={`${report.id}-${index}`}>• {finding.text}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}

                    {visualAi && limitations.length > 0 ? (
                      <p className="mt-3 text-xs leading-5 text-amber-700">
                        Sınırlamalar: {limitations.join(' · ')}
                      </p>
                    ) : null}
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
