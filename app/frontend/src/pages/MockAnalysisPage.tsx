import { useMemo, useState, type ChangeEvent } from 'react';

import { createEmptyClinicalIntake } from '../components/clinical/ClinicalIntakeForm';
import {
  uploadLabReportPdf,
  type LabAnalysisResponse,
  type LabAnalysisResult,
  type LabResultStatus,
} from '../services/labAnalysisClient';

type ResultTone = 'low' | 'high' | 'review';

type LabUploadResult = {
  fileName: string;
  result?: LabAnalysisResponse;
  error?: string;
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
  description,
  results,
  tone,
}: {
  title: string;
  description: string;
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
      <div
        className={`flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between ${header}`}
      >
        <div>
          <h3 className="font-semibold">{title}</h3>
          <p className="mt-1 text-sm opacity-80">{description}</p>
        </div>
        <span className="text-sm font-semibold">{results.length} sonuç</span>
      </div>
      <div className="overflow-x-auto bg-white">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              {['Test', 'Sonuç', 'Referans Aralığı', 'Durum', 'Açıklama'].map(
                (heading) => (
                  <th
                    key={heading}
                    className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500"
                  >
                    {heading}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 bg-white">
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
  const [backendError, setBackendError] = useState('');
  const [isUploading, setIsUploading] = useState(false);
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

  function addFiles(event: ChangeEvent<HTMLInputElement>) {
    const incoming = Array.from(event.target.files ?? []).filter((file) =>
      file.name.toLowerCase().endsWith('.pdf'),
    );

    setSelectedFiles((current) => {
      const existing = new Set(current.map(fileKey));
      return [...current, ...incoming.filter((file) => !existing.has(fileKey(file)))];
    });
    setUploadResults([]);
    setBackendError('');
    event.target.value = '';
  }

  function removeFile(file: File) {
    setSelectedFiles((current) =>
      current.filter((item) => fileKey(item) !== fileKey(file)),
    );
    setUploadResults([]);
    setBackendError('');
  }

  async function handleUpload() {
    if (selectedFiles.length === 0) {
      setBackendError('Önce en az bir PDF dosyası seçmelisin.');
      return;
    }

    setIsUploading(true);
    setBackendError('');
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
        nextResults.push({ fileName: file.name, result });
      } catch (error) {
        failedFiles.push(file);
        nextResults.push({
          fileName: file.name,
          error:
            error instanceof Error
              ? error.message
              : 'Laboratuvar analizi başarısız oldu.',
        });
      }

      setUploadResults([...nextResults]);
    }

    setBackendResult(latestSuccessful);
    setSelectedFiles(failedFiles);
    setProgress('');
    setIsUploading(false);

    if (!latestSuccessful) {
      setBackendError('Seçilen PDF dosyalarının hiçbiri analiz edilemedi.');
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-950">Laboratuvar Raporları</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          Bir veya daha fazla laboratuvar PDF&apos;si yükleyin. Raporlar analiz edilip kaydedilir.
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

        {selectedFiles.length > 0 ? (
          <div className="mt-4 space-y-2">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-slate-900">
                Seçilen dosyalar ({selectedFiles.length})
              </p>
              <button
                type="button"
                onClick={() => {
                  setSelectedFiles([]);
                  setUploadResults([]);
                  setBackendError('');
                }}
                disabled={isUploading}
                className="text-xs font-semibold text-slate-500 hover:text-red-600 disabled:opacity-50"
              >
                Temizle
              </button>
            </div>

            <div className="max-h-48 space-y-2 overflow-y-auto">
              {selectedFiles.map((file) => (
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
                    onClick={() => removeFile(file)}
                    disabled={isUploading}
                    className="shrink-0 text-xs font-semibold text-red-600 disabled:opacity-50"
                  >
                    Kaldır
                  </button>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <button
          type="button"
          onClick={handleUpload}
          disabled={isUploading || selectedFiles.length === 0}
          className="mt-4 w-full rounded-lg bg-blue-700 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {isUploading
            ? progress || 'Analiz ediliyor…'
            : selectedFiles.length > 1
              ? `${selectedFiles.length} PDF’yi analiz et`
              : 'PDF’yi analiz et'}
        </button>
      </section>

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
              <strong>{item.fileName}</strong>
              <span className="ml-2">
                {item.error
                  ? `— ${item.error}`
                  : `— analiz edildi (${item.result?.counts.total ?? 0} sonuç)`}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {backendError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {backendError}
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

          <ResultGroup
            title="Yüksek Sonuçlar"
            description="Referans aralığının üzerindeki sonuçlar."
            results={groupedResults.high}
            tone="high"
          />
          <ResultGroup
            title="Düşük Sonuçlar"
            description="Referans aralığının altındaki sonuçlar."
            results={groupedResults.low}
            tone="low"
          />
          <ResultGroup
            title="Hekim Kontrolü Gerekenler"
            description="Belirsiz veya referans bilgisi yetersiz sonuçlar."
            results={groupedResults.review}
            tone="review"
          />
        </section>
      ) : null}
    </div>
  );
}
