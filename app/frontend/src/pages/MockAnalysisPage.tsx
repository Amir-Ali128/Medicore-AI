import { useMemo, useState, type ChangeEvent } from 'react';

import {
  createEmptyClinicalIntake,
  readStoredClinicalIntake,
} from '../components/clinical/ClinicalIntakeForm';
import {
  uploadLabReportPdf,
  type LabAnalysisResponse,
  type LabAnalysisResult,
  type LabResultStatus,
} from '../services/labAnalysisClient';
import { saveLabReportToPatient } from '../services/labArchiveClient';
import { getActivePatientId } from '../services/patientClient';

type ResultTone = 'low' | 'high' | 'review';

type LabUploadResult = {
  fileName: string;
  result?: LabAnalysisResponse;
  error?: string;
  saveError?: string;
  saved?: boolean;
};

function fileKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function statusLabel(status: string) {
  return status.replace(/_/g, ' ').toUpperCase();
}

function statusClassName(status: string) {
  if (status === 'high') return 'border-red-200 bg-red-50 text-red-700';
  if (status === 'low') return 'border-amber-200 bg-amber-50 text-amber-800';
  return 'border-violet-200 bg-violet-50 text-violet-700';
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

  function addFiles(event: ChangeEvent<HTMLInputElement>) {
    const incoming = Array.from(event.target.files ?? []).filter((file) =>
      file.name.toLowerCase().endsWith('.pdf'),
    );

    setSelectedFiles((current) => {
      const existing = new Set(current.map(fileKey));
      return [...current, ...incoming.filter((file) => !existing.has(fileKey(file)))];
    });
    setUploadResults([]);
    setMessage('');
    setError('');
    event.target.value = '';
  }

  async function handleUpload() {
    const patientId = getActivePatientId();
    if (!patientId) {
      setError('Önce Hasta Bilgileri bölümünde Kaydet’e basarak aktif hasta kaydını oluşturmalısın.');
      return;
    }
    if (selectedFiles.length === 0) {
      setError('Önce en az bir PDF dosyası seçmelisin.');
      return;
    }

    const clinicalContext = readStoredClinicalIntake() ?? createEmptyClinicalIntake();
    setIsUploading(true);
    setError('');
    setMessage('');
    setUploadResults([]);

    const nextResults: LabUploadResult[] = [];
    const failedFiles: File[] = [];
    let latestSuccessful: LabAnalysisResponse | null = null;

    for (let index = 0; index < selectedFiles.length; index += 1) {
      const file = selectedFiles[index];
      setProgress(`${index + 1}/${selectedFiles.length} · ${file.name} analiz ediliyor`);

      try {
        const result = await uploadLabReportPdf(file, createEmptyClinicalIntake());
        latestSuccessful = result;

        try {
          setProgress(`${index + 1}/${selectedFiles.length} · ${file.name} kaydediliyor`);
          await saveLabReportToPatient(
            result.lab_report_id,
            patientId,
            clinicalContext,
            result.patient,
          );
          nextResults.push({ fileName: file.name, result, saved: true });
        } catch (saveError) {
          nextResults.push({
            fileName: file.name,
            result,
            saved: false,
            saveError:
              saveError instanceof Error
                ? saveError.message
                : 'Analiz edildi ancak arşive otomatik kaydedilemedi.',
          });
        }
      } catch (uploadError) {
        failedFiles.push(file);
        nextResults.push({
          fileName: file.name,
          error:
            uploadError instanceof Error
              ? uploadError.message
              : 'Laboratuvar analizi başarısız oldu.',
        });
      }
      setUploadResults([...nextResults]);
    }

    setBackendResult(latestSuccessful);
    setSelectedFiles(failedFiles);
    setProgress('');
    setIsUploading(false);

    const analyzed = nextResults.filter((item) => item.result).length;
    const saved = nextResults.filter((item) => item.saved).length;
    const pending = nextResults.filter((item) => item.result && !item.saved).length;

    if (saved > 0 && pending === 0) {
      setMessage(`${saved} laboratuvar raporu analiz edildi ve hastanın arşivine kaydedildi.`);
    } else if (analyzed > 0 && pending > 0) {
      setMessage(`${analyzed} rapor analiz edildi. Kaydedilemeyen ${pending} rapor için Kaydet’e basabilirsin.`);
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
      setMessage(`${savedIds.size} laboratuvar raporu hastanın arşivine kaydedildi.`);
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
          PDF&apos;yi analiz ettiğinde sonuçlar aktif hastaya otomatik kaydedilir. Kaydet düğmesi de ekranda kalır.
        </p>
      </header>

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <input
          type="file"
          accept="application/pdf,.pdf"
          multiple
          onChange={addFiles}
          className="block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-700 file:px-4 file:py-2.5 file:text-sm file:font-semibold file:text-white hover:file:bg-blue-800"
        />
        <p className="mt-3 text-xs leading-5 text-amber-700">
          Dosyalarda isim, soyisim, T.C. kimlik numarası veya benzeri doğrudan kişisel tanımlayıcılar bulunmamalıdır.
        </p>

        {selectedFiles.length > 0 ? (
          <div className="mt-4 space-y-2">
            {selectedFiles.map((file) => (
              <div
                key={fileKey(file)}
                className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2"
              >
                <span className="truncate text-sm font-medium text-slate-900">{file.name}</span>
                <button
                  type="button"
                  onClick={() =>
                    setSelectedFiles((current) =>
                      current.filter((item) => fileKey(item) !== fileKey(file)),
                    )
                  }
                  disabled={isUploading}
                  className="ml-3 text-xs font-semibold text-red-600 disabled:opacity-50"
                >
                  Kaldır
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
        </div>
      </section>

      {uploadResults.length > 0 ? (
        <div className="space-y-2">
          {uploadResults.map((item) => (
            <div
              key={item.fileName}
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
                    ? `— analiz edildi ve arşive kaydedildi (${item.result?.counts.total ?? 0} sonuç)`
                    : `— analiz edildi ancak henüz kaydedilemedi (${item.result?.counts.total ?? 0} sonuç)`}
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
          {savedCount} rapor bu oturumda aktif hastanın arşivine kaydedildi.
        </p>
      ) : null}
    </div>
  );
}
