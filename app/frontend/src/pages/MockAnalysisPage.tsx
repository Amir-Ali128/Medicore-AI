import { useEffect, useMemo, useState, type ChangeEvent } from 'react';

import {
  createEmptyClinicalIntake,
  readStoredClinicalIntake,
} from '../components/clinical/ClinicalIntakeForm';
import ManualLabEntrySection from '../components/lab/ManualLabEntrySection';
import {
  analyzeLabReportImage,
  getLatestAnalysisForLabReport,
  type LabAnalysisResponse,
  type LabAnalysisResult,
  type LabReportSummary,
} from '../services/labAnalysisClient';
import { uploadLabReportPdfDirect } from '../services/labPdfDirectClient';
import {
  deleteLabReport,
  listPatientLabReports,
  openLabReportPdf,
  saveLabReportToPatient,
  uploadLabReportOriginalFile,
} from '../services/labArchiveClient';
import { getActivePatientId } from '../services/patientClient';

type ResultTone = 'normal' | 'low' | 'high' | 'review';

type LabUploadResult = {
  fileName: string;
  originalFile?: File;
  result?: LabAnalysisResponse;
  error?: string;
  saveError?: string;
  saved?: boolean;
};

const OPEN_LOW_SENTINEL = -100_000_000;
const OPEN_HIGH_SENTINEL = 100_000_000;

function fileKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function isImageLabFile(file: File) {
  return /\.jpe?g$/i.test(file.name) || file.type === 'image/jpeg';
}

function isSupportedLabFile(file: File) {
  return file.name.toLowerCase().endsWith('.pdf') || isImageLabFile(file);
}

function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(String(value).replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : null;
}

function effectiveStatus(result: LabAnalysisResult): ResultTone {
  const value = toNumber(result.normalized_value);
  const min = toNumber(result.reference_min);
  const max = toNumber(result.reference_max);

  if (value !== null && min !== null && max !== null) {
    const openLow = min <= OPEN_LOW_SENTINEL;
    const openHigh = max >= OPEN_HIGH_SENTINEL;

    if (openLow && !openHigh) {
      return value > max ? 'high' : 'normal';
    }
    if (!openLow && openHigh) {
      return value < min ? 'low' : 'normal';
    }
    if (!openLow && !openHigh) {
      if (value < min) return 'low';
      if (value > max) return 'high';
      return 'normal';
    }
  }

  if (result.result_status === 'high') return 'high';
  if (result.result_status === 'low') return 'low';
  if (result.result_status === 'normal') return 'normal';
  return 'review';
}

function statusLabel(status: ResultTone) {
  if (status === 'normal') return 'NORMAL';
  if (status === 'high') return 'YÜKSEK';
  if (status === 'low') return 'DÜŞÜK';
  return 'HEKİM KONTROLÜ';
}

function statusClassName(status: ResultTone) {
  if (status === 'normal') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'high') return 'border-red-200 bg-red-50 text-red-700';
  if (status === 'low') return 'border-amber-200 bg-amber-50 text-amber-800';
  return 'border-violet-200 bg-violet-50 text-violet-700';
}

function formatArchiveDate(value: string | null) {
  if (!value) return 'Tarih yok';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium' }).format(parsed);
}

function hasStoredOriginalPdf(report: LabReportSummary) {
  return report.metadata_json?.original_file_stored === true;
}

function archiveReportLabel(report: LabReportSummary) {
  const fileName = report.file_name ?? '';
  if (fileName.toLowerCase().endsWith('.pdf')) return fileName || 'Laboratuvar raporu.pdf';
  if (fileName.startsWith('manual-entry-')) return 'Manuel laboratuvar girişi';
  if (/\.jpe?g$/i.test(fileName)) return fileName || 'Laboratuvar fotoğrafı';
  return fileName || 'Laboratuvar kaydı';
}

function displayTestName(result: LabAnalysisResult) {
  // PDF satırındaki gerçek ad, eski alias eşleştirmelerinden daha güvenlidir.
  return result.raw_parameter_name || result.canonical_name || 'Bilinmeyen test';
}

function formatReference(result: LabAnalysisResult) {
  const min = toNumber(result.reference_min);
  const max = toNumber(result.reference_max);
  const unit = result.unit ? ` ${result.unit}` : '';

  if (min === null && max === null) return 'Hekim kontrolü gerekli';
  if (min !== null && min <= OPEN_LOW_SENTINEL && max !== null) {
    return `< ${max}${unit}`;
  }
  if (max !== null && max >= OPEN_HIGH_SENTINEL && min !== null) {
    return `> ${min}${unit}`;
  }
  return `${result.reference_min ?? '-'} - ${result.reference_max ?? '-'}${unit}`;
}

function displayReason(result: LabAnalysisResult) {
  const status = effectiveStatus(result);
  if (status === 'normal') return 'Değer PDF’de belirtilen referans sınırları içindedir.';
  if (status === 'high') return 'Değer PDF’de belirtilen üst referans sınırının üzerindedir.';
  if (status === 'low') return 'Değer PDF’de belirtilen alt referans sınırının altındadır.';
  return 'PDF’de güvenilir bir referans aralığı bulunmadığı için hekim kontrolü gerekir.';
}

function StatusPill({ status }: { status: ResultTone }) {
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${statusClassName(status)}`}>
      {statusLabel(status)}
    </span>
  );
}

function ResultGroup({
  title,
  results,
  tone,
}: {
  title: string;
  results: LabAnalysisResult[];
  tone: ResultTone;
}) {
  if (results.length === 0) return null;

  const border =
    tone === 'normal'
      ? 'border-emerald-200'
      : tone === 'high'
        ? 'border-red-200'
        : tone === 'low'
          ? 'border-amber-200'
          : 'border-violet-200';
  const header =
    tone === 'normal'
      ? 'bg-emerald-50 text-emerald-800'
      : tone === 'high'
        ? 'bg-red-50 text-red-800'
        : tone === 'low'
          ? 'bg-amber-50 text-amber-800'
          : 'bg-violet-50 text-violet-800';

  return (
    <section className={`overflow-hidden rounded-xl border ${border}`}>
      <div className={`flex items-center justify-between px-4 py-3 ${header}`}>
        <h3 className="font-semibold">{title}</h3>
        <span className="text-sm font-semibold">{results.length} sonuç</span>
      </div>
      <div className="overflow-x-auto bg-white">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              {['Test', 'Sonuç', 'Referans', 'Durum', 'Açıklama'].map((heading) => (
                <th key={heading} className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {results.map((result) => {
              const status = effectiveStatus(result);
              return (
                <tr key={result.lab_result_id}>
                  <td className="px-4 py-4 font-medium text-slate-950">{displayTestName(result)}</td>
                  <td className="whitespace-nowrap px-4 py-4 text-slate-700">
                    {result.normalized_value} {result.unit}
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-slate-600">{formatReference(result)}</td>
                  <td className="px-4 py-4"><StatusPill status={status} /></td>
                  <td className="max-w-md px-4 py-4 text-sm leading-6 text-slate-600">{displayReason(result)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function MockAnalysisPage() {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadResults, setUploadResults] = useState<LabUploadResult[]>([]);
  const [backendResult, setBackendResult] = useState<LabAnalysisResponse | null>(null);
  const [archivedReports, setArchivedReports] = useState<LabReportSummary[]>([]);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [archiveError, setArchiveError] = useState('');
  const [openingPdfId, setOpeningPdfId] = useState<string | null>(null);
  const [deletingPdfId, setDeletingPdfId] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [progress, setProgress] = useState('');
  const [savingFileKey, setSavingFileKey] = useState<string | null>(null);

  const groupedResults = useMemo(() => {
    const results = backendResult?.results ?? [];
    return {
      normal: results.filter((item) => effectiveStatus(item) === 'normal'),
      high: results.filter((item) => effectiveStatus(item) === 'high'),
      low: results.filter((item) => effectiveStatus(item) === 'low'),
      review: results.filter((item) => effectiveStatus(item) === 'review'),
    };
  }, [backendResult]);

  const successfulResults = uploadResults.filter((item) => Boolean(item.result));
  const unsavedResults = successfulResults.filter((item) => !item.saved);
  const savedCount = successfulResults.filter((item) => item.saved).length;

  async function refreshArchive(patientId = getActivePatientId()) {
    if (!patientId) {
      setArchivedReports([]);
      return;
    }
    setArchiveLoading(true);
    setArchiveError('');
    try {
      const reports = await listPatientLabReports(patientId);
      const sorted = [...reports].sort((a, b) => Date.parse(b.created_at ?? '') - Date.parse(a.created_at ?? ''));
      setArchivedReports(sorted);
      if (sorted[0]) {
        setBackendResult(await getLatestAnalysisForLabReport(sorted[0].id, patientId));
      } else {
        setBackendResult(null);
      }
    } catch (loadError) {
      setArchiveError(loadError instanceof Error ? loadError.message : 'Kaydedilen laboratuvar kayıtları yüklenemedi.');
    } finally {
      setArchiveLoading(false);
    }
  }

  useEffect(() => {
    void refreshArchive();
  }, []);

  function addFiles(event: ChangeEvent<HTMLInputElement>) {
    const incoming = Array.from(event.target.files ?? []).filter(isSupportedLabFile);
    setSelectedFiles((current) => {
      const existing = new Set(current.map(fileKey));
      return [...current, ...incoming.filter((file) => !existing.has(fileKey(file)))];
    });
    setMessage('');
    setError('');
    event.target.value = '';
  }

  function removeSelectedFile(file: File) {
    setSelectedFiles((current) => current.filter((item) => fileKey(item) !== fileKey(file)));
  }

  async function analyzeFile(file: File) {
    return isImageLabFile(file)
      ? analyzeLabReportImage(file, createEmptyClinicalIntake())
      : uploadLabReportPdfDirect(file, createEmptyClinicalIntake());
  }

  async function handleUpload() {
    if (!getActivePatientId()) {
      setError('Önce Hasta Bilgileri bölümünde Kaydet’e basarak aktif hasta kaydını oluşturmalısın.');
      return;
    }
    if (selectedFiles.length === 0) {
      setError('Önce en az bir PDF veya JPG dosyası seçmelisin.');
      return;
    }

    setIsUploading(true);
    setError('');
    setMessage('');
    const nextResults: LabUploadResult[] = [];
    const failedFiles: File[] = [];
    let latestSuccessful: LabAnalysisResponse | null = null;

    for (let index = 0; index < selectedFiles.length; index += 1) {
      const file = selectedFiles[index];
      setProgress(`${index + 1}/${selectedFiles.length} · ${file.name} analiz ediliyor`);
      try {
        const result = await analyzeFile(file);
        latestSuccessful = result;
        nextResults.push({ fileName: file.name, originalFile: file, result, saved: false });
      } catch (uploadError) {
        failedFiles.push(file);
        nextResults.push({
          fileName: file.name,
          originalFile: file,
          error: uploadError instanceof Error ? uploadError.message : 'Laboratuvar analizi başarısız oldu.',
        });
      }
    }

    setUploadResults((current) => [...current, ...nextResults]);
    setBackendResult(latestSuccessful);
    setSelectedFiles(failedFiles);
    setProgress('');
    setIsUploading(false);

    const analyzed = nextResults.filter((item) => item.result).length;
    if (analyzed > 0) setMessage(`${analyzed} laboratuvar raporu analiz edildi. Arşive eklemek için Kaydet’e bas.`);
    else setError('Seçilen dosyaların hiçbiri analiz edilemedi.');
  }

  async function saveAnalyzedItem(item: LabUploadResult, patientId: string) {
    if (!item.result) return;
    const clinicalContext = readStoredClinicalIntake() ?? createEmptyClinicalIntake();
    await saveLabReportToPatient(item.result.lab_report_id, patientId, clinicalContext, item.result.patient);
    if (item.originalFile && !isImageLabFile(item.originalFile)) {
      await uploadLabReportOriginalFile(item.result.lab_report_id, item.originalFile);
    }
  }

  async function handleSaveFile(file: File) {
    const patientId = getActivePatientId();
    if (!patientId) {
      setError('Önce Hasta Bilgileri bölümünde Kaydet’e basarak aktif hasta kaydını oluşturmalısın.');
      return;
    }
    setSavingFileKey(fileKey(file));
    setError('');
    try {
      const result = await analyzeFile(file);
      const item: LabUploadResult = { fileName: file.name, originalFile: file, result, saved: false };
      await saveAnalyzedItem(item, patientId);
      setUploadResults((current) => [...current, { ...item, saved: true }]);
      setBackendResult(result);
      setSelectedFiles((current) => current.filter((candidate) => fileKey(candidate) !== fileKey(file)));
      await refreshArchive(patientId);
      setMessage(`${file.name} analiz edildi ve hastanın arşivine kaydedildi.`);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : `${file.name} kaydedilemedi.`);
    } finally {
      setSavingFileKey(null);
    }
  }

  async function handleSave() {
    const patientId = getActivePatientId();
    if (!patientId || unsavedResults.length === 0) return;
    setIsSaving(true);
    setError('');
    const savedIds = new Set<string>();
    const failedMessages: string[] = [];

    for (const item of unsavedResults) {
      try {
        await saveAnalyzedItem(item, patientId);
        if (item.result) savedIds.add(item.result.lab_report_id);
      } catch (saveError) {
        failedMessages.push(saveError instanceof Error ? saveError.message : `${item.fileName} arşive kaydedilemedi.`);
      }
    }

    setUploadResults((current) => current.map((item) => item.result && savedIds.has(item.result.lab_report_id) ? { ...item, saved: true, saveError: undefined } : item));
    if (savedIds.size > 0) {
      await refreshArchive(patientId);
      setMessage(`${savedIds.size} laboratuvar raporu hastanın arşivine kaydedildi.`);
    }
    if (failedMessages[0]) setError(failedMessages[0]);
    setIsSaving(false);
  }

  async function handleOpenPdf(report: LabReportSummary) {
    setOpeningPdfId(report.id);
    setArchiveError('');
    try {
      await openLabReportPdf(report.id, report.file_name);
    } catch (openError) {
      setArchiveError(openError instanceof Error ? openError.message : 'PDF açılamadı.');
    } finally {
      setOpeningPdfId(null);
    }
  }

  async function handleDeleteArchivedPdf(report: LabReportSummary) {
    if (!window.confirm(`${archiveReportLabel(report)} arşivden kalıcı olarak silinsin mi?`)) return;
    setDeletingPdfId(report.id);
    try {
      await deleteLabReport(report.id);
      await refreshArchive();
    } catch (deleteError) {
      setArchiveError(deleteError instanceof Error ? deleteError.message : 'Laboratuvar kaydı silinemedi.');
    } finally {
      setDeletingPdfId(null);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-950">Laboratuvar Raporları</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          PDF’deki test adı, sonuç ve referans aralığı esas alınır. Sonuçlar normal, yüksek, düşük veya yalnızca referansı yoksa hekim kontrolü olarak ayrılır.
        </p>
      </header>

      <ManualLabEntrySection
        onAnalyzed={(result) => { setBackendResult(result); setError(''); }}
        onSaved={async (result) => { setBackendResult(result); await refreshArchive(result.patient_id); setMessage('Manuel laboratuvar kaydı aktif hastanın arşivine eklendi.'); }}
      />

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="text-base font-semibold text-slate-950">PDF veya JPG ile laboratuvar girişi</h2>
        <p className="mt-1 text-sm leading-6 text-slate-500">
          PDF yüklemeleri doğrudan PDF-first parser ile analiz edilir; eski alias eşleştirmesi sonuçların yerini değiştirmez.
        </p>
        <input
          type="file"
          accept="application/pdf,.pdf,image/jpeg,.jpg,.jpeg"
          multiple
          onChange={addFiles}
          className="mt-4 block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-700 file:px-4 file:py-2.5 file:text-sm file:font-semibold file:text-white hover:file:bg-blue-800"
        />

        {selectedFiles.length > 0 ? (
          <div className="mt-4 space-y-2">
            {selectedFiles.map((file) => (
              <div key={fileKey(file)} className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2">
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-900">{file.name}</span>
                <button type="button" onClick={() => void handleSaveFile(file)} disabled={isUploading || savingFileKey === fileKey(file)} className="rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">
                  {savingFileKey === fileKey(file) ? 'Kaydediliyor…' : 'Kaydet'}
                </button>
                <button type="button" onClick={() => removeSelectedFile(file)} disabled={isUploading} className="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-700">Sil</button>
              </div>
            ))}
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" onClick={handleUpload} disabled={isUploading || selectedFiles.length === 0} className="rounded-lg bg-blue-700 px-5 py-3 text-sm font-semibold text-white disabled:opacity-50">
            {isUploading ? progress || 'Analiz ediliyor…' : 'PDF’yi analiz et'}
          </button>
          {successfulResults.length > 0 ? (
            <button type="button" onClick={handleSave} disabled={isSaving || unsavedResults.length === 0} className="rounded-lg bg-emerald-700 px-5 py-3 text-sm font-semibold text-white disabled:opacity-50">
              {isSaving ? 'Kaydediliyor…' : unsavedResults.length > 0 ? 'Kaydet' : '✓ Kaydedildi'}
            </button>
          ) : null}
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-950">Kaydedilen laboratuvar kayıtları</h2>
            <p className="mt-1 text-sm text-slate-500">Aktif hastaya bağlı laboratuvar raporları.</p>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">{archivedReports.length} kayıt</span>
        </div>

        {archiveLoading ? <p className="mt-4 text-sm text-slate-500">Yükleniyor…</p> : archiveError ? (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{archiveError}</div>
        ) : (
          <div className="mt-4 space-y-2">
            {archivedReports.map((report) => {
              const isPdf = report.file_name?.toLowerCase().endsWith('.pdf') ?? false;
              const canOpen = isPdf && hasStoredOriginalPdf(report);
              return (
                <div key={report.id} className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">{archiveReportLabel(report)}</p>
                    <p className="mt-1 text-xs text-slate-500">{formatArchiveDate(report.report_date || report.created_at)}</p>
                  </div>
                  <div className="flex gap-2">
                    {canOpen ? <button type="button" onClick={() => void handleOpenPdf(report)} disabled={openingPdfId === report.id} className="rounded-lg border border-emerald-200 bg-white px-3 py-2 text-xs font-semibold text-emerald-700">PDF’yi aç</button> : null}
                    <button type="button" onClick={() => void handleDeleteArchivedPdf(report)} disabled={deletingPdfId === report.id} className="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-700">{deletingPdfId === report.id ? 'Siliniyor…' : 'Sil'}</button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {message ? <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">{message}</div> : null}
      {error ? <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div> : null}

      {backendResult ? (
        <section className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {[
              ['Toplam', backendResult.results.length, 'border-slate-200'],
              ['Normal', groupedResults.normal.length, 'border-emerald-200'],
              ['Yüksek', groupedResults.high.length, 'border-red-200'],
              ['Düşük', groupedResults.low.length, 'border-amber-200'],
              ['Kontrol gereken', groupedResults.review.length, 'border-violet-200'],
            ].map(([label, value, border]) => (
              <div key={String(label)} className={`rounded-xl border ${border} bg-white p-4`}>
                <p className="text-sm text-slate-500">{label}</p>
                <p className="mt-1 text-2xl font-semibold">{value}</p>
              </div>
            ))}
          </div>

          <ResultGroup title="Yüksek Sonuçlar" results={groupedResults.high} tone="high" />
          <ResultGroup title="Düşük Sonuçlar" results={groupedResults.low} tone="low" />
          <ResultGroup title="Normal Sonuçlar" results={groupedResults.normal} tone="normal" />
          <ResultGroup title="Hekim Kontrolü Gerekenler" results={groupedResults.review} tone="review" />
        </section>
      ) : null}

      {savedCount > 0 ? <p className="text-xs text-slate-500">{savedCount} laboratuvar raporu bu oturumda aktif hastanın arşivine kaydedildi.</p> : null}
    </div>
  );
}
