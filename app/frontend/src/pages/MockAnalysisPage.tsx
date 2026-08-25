import { useEffect, useMemo, useState, type ChangeEvent } from 'react';

import {
  createEmptyClinicalIntake,
  readStoredClinicalIntake,
} from '../components/clinical/ClinicalIntakeForm';
import ManualLabEntrySection from '../components/lab/ManualLabEntrySection';
import {
  analyzeLabReportImage,
  uploadLabReportPdf,
  type LabAnalysisResponse,
  type LabAnalysisResult,
  type LabReportSummary,
  type LabResultStatus,
} from '../services/labAnalysisClient';
import {
  deleteLabReport,
  listPatientLabReports,
  openLabReportPdf,
  saveLabReportToPatient,
  uploadLabReportOriginalFile,
} from '../services/labArchiveClient';
import { getActivePatientId } from '../services/patientClient';

type ResultTone = 'low' | 'high' | 'review';

type LabUploadResult = {
  fileName: string;
  originalFile?: File;
  result?: LabAnalysisResponse;
  error?: string;
  saveError?: string;
  saved?: boolean;
};

function fileKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function isImageLabFile(file: File) {
  return /\.jpe?g$/i.test(file.name) || file.type === 'image/jpeg';
}

function isSupportedLabFile(file: File) {
  return file.name.toLowerCase().endsWith('.pdf') || isImageLabFile(file);
}

function statusLabel(status: string) {
  return status.replace(/_/g, ' ').toUpperCase();
}

function statusClassName(status: string) {
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
  if (fileName.toLowerCase().endsWith('.pdf')) {
    return fileName || 'Laboratuvar raporu.pdf';
  }
  if (fileName.startsWith('manual-entry-')) {
    return 'Manuel laboratuvar girişi';
  }
  if (/\.jpe?g$/i.test(fileName)) {
    return fileName || 'Laboratuvar fotoğrafı';
  }
  return fileName || 'Laboratuvar kaydı';
}

function archiveSourceDescription(report: LabReportSummary) {
  const fileName = report.file_name ?? '';
  if (fileName.startsWith('manual-entry-')) {
    return 'Manuel laboratuvar girişi';
  }
  if (/\.jpe?g$/i.test(fileName)) {
    return 'Fotoğraftan laboratuvar girişi';
  }
  return 'Laboratuvar kaydı';
}

function StatusPill({ status }: { status: LabResultStatus | string }) {
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${statusClassName(status)}`}
    >
      {statusLabel(status)}
    </span>
  );
}

function formatReference(result: LabAnalysisResult) {
  if (result.reference_min === null && result.reference_max === null) {
    return 'Hekim kontrolü gerekli';
  }
  return `${result.reference_min ?? '-'} - ${result.reference_max ?? '-'} ${result.unit ?? ''}`;
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
    tone === 'high'
      ? 'border-red-200'
      : tone === 'low'
        ? 'border-amber-200'
        : 'border-violet-200';
  const header =
    tone === 'high'
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
                <th
                  key={heading}
                  className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500"
                >
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {results.map((result) => (
              <tr key={result.lab_result_id}>
                <td className="px-4 py-4 font-medium text-slate-950">
                  {result.canonical_name ?? result.raw_parameter_name}
                </td>
                <td className="whitespace-nowrap px-4 py-4 text-slate-700">
                  {result.normalized_value} {result.unit}
                </td>
                <td className="whitespace-nowrap px-4 py-4 text-slate-600">
                  {formatReference(result)}
                </td>
                <td className="px-4 py-4">
                  <StatusPill status={result.result_status} />
                </td>
                <td className="max-w-md px-4 py-4 text-sm leading-6 text-slate-600">
                  {result.reason}
                </td>
              </tr>
            ))}
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

  const groupedResults = useMemo(() => {
    const results = backendResult?.results ?? [];
    return {
      high: results.filter((item) => item.result_status === 'high'),
      low: results.filter((item) => item.result_status === 'low'),
      review: results.filter(
        (item) =>
          item.result_status === 'needs_review' || item.result_status === 'unknown',
      ),
    };
  }, [backendResult]);

  const successfulResults = uploadResults.filter((item) => Boolean(item.result));
  const unsavedResults = successfulResults.filter((item) => !item.saved);
  const savedCount = successfulResults.filter((item) => item.saved).length;
  const archivedRecords = archivedReports;

  async function refreshArchive(patientId = getActivePatientId()) {
    if (!patientId) {
      setArchivedReports([]);
      return;
    }

    setArchiveLoading(true);
    setArchiveError('');
    try {
      const reports = await listPatientLabReports(patientId);
      setArchivedReports(
        [...reports].sort(
          (a, b) => Date.parse(b.created_at ?? '') - Date.parse(a.created_at ?? ''),
        ),
      );
    } catch (loadError) {
      setArchiveError(
        loadError instanceof Error
          ? loadError.message
          : 'Kaydedilen laboratuvar kayıtları yüklenemedi.',
      );
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
    setSelectedFiles((current) =>
      current.filter((item) => fileKey(item) !== fileKey(file)),
    );
    setMessage('');
    setError('');
  }

  function clearSelectedFiles() {
    setSelectedFiles([]);
    setMessage('Seçilen dosyalar yükleme listesinden silindi.');
    setError('');
  }

  async function handleOpenPdf(report: LabReportSummary) {
    setOpeningPdfId(report.id);
    setArchiveError('');
    try {
      await openLabReportPdf(report.id, report.file_name);
    } catch (openError) {
      setArchiveError(
        openError instanceof Error ? openError.message : 'PDF açılamadı.',
      );
    } finally {
      setOpeningPdfId(null);
    }
  }

  async function handleDeleteArchivedPdf(report: LabReportSummary) {
    const label = archiveReportLabel(report);
    const confirmed = window.confirm(`${label} arşivden kalıcı olarak silinsin mi?`);
    if (!confirmed) return;

    setDeletingPdfId(report.id);
    setArchiveError('');
    setMessage('');
    try {
      await deleteLabReport(report.id);
      setArchivedReports((current) => current.filter((item) => item.id !== report.id));
      setUploadResults((current) =>
        current.filter((item) => item.result?.lab_report_id !== report.id),
      );
      if (backendResult?.lab_report_id === report.id) {
        setBackendResult(null);
      }
      setMessage(`${label} arşivden silindi.`);
    } catch (deleteError) {
      setArchiveError(
        deleteError instanceof Error
          ? deleteError.message
          : 'Laboratuvar kaydı silinemedi.',
      );
    } finally {
      setDeletingPdfId(null);
    }
  }

  async function handleUpload() {
    if (!getActivePatientId()) {
      setError('Önce Hasta Bilgileri bölümünde Kaydet’e basarak aktif hasta kaydını oluşturmalısın.');
      return;
    }
    if (selectedFiles.length === 0) {
      setError('Önce en az bir PDF dosyası veya JPG ekran görüntüsü seçmelisin.');
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

      let completedItem: LabUploadResult;
      try {
        const result = isImageLabFile(file)
          ? await analyzeLabReportImage(file, createEmptyClinicalIntake())
          : await uploadLabReportPdf(file, createEmptyClinicalIntake());
        latestSuccessful = result;
        completedItem = {
          fileName: file.name,
          originalFile: file,
          result,
          saved: false,
        };
      } catch (uploadError) {
        failedFiles.push(file);
        completedItem = {
          fileName: file.name,
          originalFile: file,
          error:
            uploadError instanceof Error
              ? uploadError.message
              : 'Laboratuvar analizi başarısız oldu.',
        };
      }

      nextResults.push(completedItem);
      setUploadResults((current) => [...current, completedItem]);
    }

    setBackendResult(latestSuccessful);
    setSelectedFiles(failedFiles);
    setProgress('');
    setIsUploading(false);

    const analyzed = nextResults.filter((item) => item.result).length;
    if (analyzed > 0) {
      setMessage(`${analyzed} laboratuvar raporu analiz edildi. Kalıcı arşive eklemek için Kaydet’e bas.`);
    } else if (!latestSuccessful) {
      setError('Seçilen PDF dosyalarının hiçbiri analiz edilemedi.');
    }
  }

  async function handleSave() {
    const patientId = getActivePatientId();
    if (!patientId) {
      setError('Aktif hasta bulunamadı. Önce Hasta Bilgileri bölümünde Kaydet’e bas.');
      return;
    }
    if (unsavedResults.length === 0) return;

    const clinicalContext = readStoredClinicalIntake() ?? createEmptyClinicalIntake();
    setIsSaving(true);
    setError('');
    setMessage('');

    const savedIds = new Set<string>();
    const failedMessages: string[] = [];

    for (const item of unsavedResults) {
      if (!item.result) continue;
      try {
        await saveLabReportToPatient(
          item.result.lab_report_id,
          patientId,
          clinicalContext,
          item.result.patient,
        );
        if (!item.originalFile || !isImageLabFile(item.originalFile)) {
          if (!item.originalFile) {
            throw new Error(`${item.fileName} için PDF yeniden seçilmeden kaydedilemez.`);
          }
          await uploadLabReportOriginalFile(item.result.lab_report_id, item.originalFile);
        }
        savedIds.add(item.result.lab_report_id);
      } catch (saveError) {
        failedMessages.push(
          saveError instanceof Error
            ? saveError.message
            : `${item.fileName} arşive kaydedilemedi.`,
        );
      }
    }

    setUploadResults((current) =>
      current.map((item) => {
        if (!item.result) return item;
        if (savedIds.has(item.result.lab_report_id)) {
          return { ...item, saved: true, saveError: undefined };
        }
        return item;
      }),
    );

    if (savedIds.size > 0) {
      await refreshArchive(patientId);
      setMessage(`${savedIds.size} laboratuvar raporu anonimleştirilmiş PDF ile hastanın arşivine kaydedildi.`);
    }
    if (failedMessages.length > 0) {
      setError(failedMessages[0]);
    }
    setIsSaving(false);
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-950">Laboratuvar Raporları</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          Sonuçları PDF&apos;den analiz edebilir veya manuel girebilirsin. Her iki akışta da analizden sonra ayrıca Kaydet&apos;e basarak aktif hastanın arşivine ekle.
        </p>
      </header>

      <ManualLabEntrySection
        onAnalyzed={(result) => {
          setBackendResult(result);
          setError('');
        }}
        onSaved={async (result) => {
          setBackendResult(result);
          await refreshArchive(result.patient_id);
          setMessage('Manuel laboratuvar kaydı aktif hastanın arşivine eklendi.');
          setError('');
        }}
      />

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <div>
          <h2 className="text-base font-semibold text-slate-950">PDF veya JPG ile laboratuvar girişi</h2>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            PDF&apos;yi ya da laboratuvar sonucunun JPG ekran görüntüsünü/fotoğrafını önce analiz et. Arşive kalıcı olarak eklemek istediğinde ayrıca Kaydet&apos;e bas; yanlış seçtiğin dosyayı Sil ile kaldırabilirsin.
          </p>
        </div>
        <input
          type="file"
          accept="application/pdf,.pdf,image/jpeg,.jpg,.jpeg"
          multiple
          onChange={addFiles}
          className="mt-4 block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-700 file:px-4 file:py-2.5 file:text-sm file:font-semibold file:text-white hover:file:bg-blue-800"
        />
        <p className="mt-3 text-xs leading-5 text-amber-700">
          Kaydet sırasında isim/soyisim, T.C. kimlik numarası, tam doğum tarihi ve benzeri doğrudan tanımlayıcılar PDF&apos;den çıkarılır. Güvenli anonimleştirme yapılamazsa PDF arşive kaydedilmez. JPG fotoğraflar arşive orijinal görsel olarak kaydedilmez; yalnızca fotoğraftan okunan test sonuçları saklanır.
        </p>

        {selectedFiles.length > 0 ? (
          <div className="mt-4 space-y-2">
            {selectedFiles.map((file) => (
              <div
                key={fileKey(file)}
                className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2"
              >
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-900">{file.name}</span>
                <button
                  type="button"
                  onClick={() => removeSelectedFile(file)}
                  disabled={isUploading}
                  className="shrink-0 rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                >
                  Sil
                </button>
              </div>
            ))}
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleUpload}
            disabled={isUploading || selectedFiles.length === 0}
            className="rounded-lg bg-blue-700 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isUploading ? progress || 'Analiz ediliyor…' : 'PDF’yi analiz et'}
          </button>

          {successfulResults.length > 0 ? (
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving || unsavedResults.length === 0}
              className="rounded-lg bg-emerald-700 px-5 py-3 text-sm font-semibold text-white hover:bg-emerald-800 disabled:cursor-default disabled:bg-emerald-100 disabled:text-emerald-800"
            >
              {isSaving
                ? 'Kaydediliyor…'
                : unsavedResults.length > 0
                  ? 'Kaydet'
                  : '✓ Kaydedildi'}
            </button>
          ) : null}

          {selectedFiles.length > 0 ? (
            <button
              type="button"
              onClick={clearSelectedFiles}
              disabled={isUploading}
              className="rounded-lg border border-red-200 bg-white px-5 py-3 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Sil
            </button>
          ) : null}
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-950">Kaydedilen laboratuvar kayıtları</h2>
            <p className="mt-1 text-sm leading-6 text-slate-500">
              Bu hastaya kaydedilen PDF ve manuel laboratuvar girişleri burada tutulur. PDF kayıtlarını açabilir, tüm kayıtları Sil ile arşivden kaldırabilirsin.
            </p>
          </div>
          <span className="shrink-0 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
            {archivedRecords.length} kayıt
          </span>
        </div>

        {archiveLoading ? (
          <p className="mt-4 text-sm text-slate-500">Kaydedilen laboratuvar kayıtları yükleniyor…</p>
        ) : archiveError ? (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            {archiveError}
          </div>
        ) : archivedRecords.length === 0 ? (
          <p className="mt-4 rounded-lg bg-slate-50 p-4 text-sm text-slate-500">
            Bu hastaya kaydedilmiş laboratuvar kaydı henüz yok.
          </p>
        ) : (
          <div className="mt-4 space-y-2">
            {archivedRecords.map((report) => {
              const isPdf = report.file_name?.toLowerCase().endsWith('.pdf') ?? false;
              const canOpen = isPdf && hasStoredOriginalPdf(report);
              const label = archiveReportLabel(report);
              return (
                <div
                  key={report.id}
                  className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-900">{label}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {formatArchiveDate(report.report_date || report.created_at)} ·{' '}
                      {isPdf
                        ? canOpen
                          ? report.metadata_json?.original_file_anonymized === true
                            ? 'Anonimleştirilmiş PDF saklandı'
                            : 'Eski kayıt · PDF saklandı'
                          : 'Eski kayıt · PDF saklanmamış'
                        : archiveSourceDescription(report)}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    {canOpen ? (
                      <button
                        type="button"
                        onClick={() => void handleOpenPdf(report)}
                        disabled={openingPdfId === report.id || deletingPdfId === report.id}
                        className="rounded-lg border border-emerald-200 bg-white px-3 py-2 text-xs font-semibold text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
                      >
                        {openingPdfId === report.id ? 'Açılıyor…' : 'PDF’yi aç'}
                      </button>
                    ) : (
                      <span className="self-center text-xs font-semibold text-slate-400">✓ Kayıt var</span>
                    )}
                    <button
                      type="button"
                      onClick={() => void handleDeleteArchivedPdf(report)}
                      disabled={deletingPdfId === report.id || openingPdfId === report.id}
                      className="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                    >
                      {deletingPdfId === report.id ? 'Siliniyor…' : 'Sil'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {uploadResults.length > 0 ? (
        <div className="space-y-2">
          {uploadResults.map((item, index) => (
            <div
              key={item.result?.lab_report_id ?? `${item.fileName}-${index}`}
              className={`rounded-lg border px-4 py-3 text-sm ${
                item.error
                  ? 'border-red-200 bg-red-50 text-red-800'
                  : item.saved
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                    : 'border-amber-200 bg-amber-50 text-amber-800'
              }`}
            >
              <strong>{item.fileName}</strong>
              <span className="ml-2">
                {item.error
                  ? `— ${item.error}`
                  : item.saved
                    ? item.originalFile && isImageLabFile(item.originalFile)
                      ? `— analiz edildi; sonuçlar kaydedildi (${item.result?.counts.total ?? 0} sonuç)`
                      : `— analiz edildi; anonimleştirilmiş PDF ve sonuçlar kaydedildi (${item.result?.counts.total ?? 0} sonuç)`
                    : `— analiz edildi; henüz kaydedilmedi (${item.result?.counts.total ?? 0} sonuç)`}
              </span>
              {item.saveError ? (
                <p className="mt-1 text-xs leading-5">{item.saveError}</p>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {message ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
          {message}
        </div>
      ) : null}
      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      {backendResult ? (
        <section className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-sm text-slate-500">Toplam</p>
              <p className="mt-1 text-2xl font-semibold">{backendResult.counts.total}</p>
            </div>
            <div className="rounded-xl border border-red-200 bg-white p-4">
              <p className="text-sm text-slate-500">Yüksek</p>
              <p className="mt-1 text-2xl font-semibold">{groupedResults.high.length}</p>
            </div>
            <div className="rounded-xl border border-amber-200 bg-white p-4">
              <p className="text-sm text-slate-500">Düşük</p>
              <p className="mt-1 text-2xl font-semibold">{groupedResults.low.length}</p>
            </div>
            <div className="rounded-xl border border-violet-200 bg-white p-4">
              <p className="text-sm text-slate-500">Kontrol gereken</p>
              <p className="mt-1 text-2xl font-semibold">{groupedResults.review.length}</p>
            </div>
          </div>

          <ResultGroup title="Yüksek Sonuçlar" results={groupedResults.high} tone="high" />
          <ResultGroup title="Düşük Sonuçlar" results={groupedResults.low} tone="low" />
          <ResultGroup title="Hekim Kontrolü Gerekenler" results={groupedResults.review} tone="review" />
        </section>
      ) : null}

      {savedCount > 0 ? (
        <p className="text-xs text-slate-500">
          {savedCount} laboratuvar raporu bu oturumda aktif hastanın arşivine kaydedildi.
        </p>
      ) : null}
    </div>
  );
}
