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
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${statusClassName(status)}`}>
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

  const border = tone === 'high' ? 'border-red-200' : tone === 'low' ? 'border-amber-200' : 'border-violet-200';
  const header = tone === 'high' ? 'bg-red-50 text-red-800' : tone === 'low' ? 'bg-amber-50 text-amber-800' : 'bg-violet-50 text-violet-800';

  return (
    <section className={`overflow-hidden rounded-xl border ${border}`}>
      <div className={`flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between ${header}`}>
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
              {['Test', 'Sonuç', 'Referans Aralığı', 'Durum', 'Açıklama'].map((heading) => (
                <th key={heading} className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">{heading}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 bg-white">
            {results.map((result) => (
              <tr key={result.lab_result_id}>
                <td className="px-4 py-4 font-medium text-slate-950">{result.canonical_name ?? result.raw_parameter_name}</td>
                <td className="whitespace-nowrap px-4 py-4 text-slate-700">{result.normalized_value} {result.unit}</td>
                <td className="whitespace-nowrap px-4 py-4 text-slate-600">{formatReference(result)}</td>
                <td className="px-4 py-4"><StatusPill status={result.result_status} /></td>
                <td className="max-w-md px-4 py-4 text-sm leading-6 text-slate-600">{result.reason}</td>
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
      review: results.filter((item) => item.result_status === 'needs_review' || item.result_status === 'unknown'),
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
          error: error instanceof Error ? error.message : 'Laboratuvar analizi başarısız oldu.',
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
    <div className="space-y-8">
      <header>
        <p className="text-sm font-semibold uppercase text-cyan-700">Laboratuvar</p>
        <h2 className="mt-2 text-3xl font-semibold text-slate-950">Laboratuvar PDF&apos;lerini yükle ve analiz et</h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          Bir veya birden fazla laboratuvar PDF&apos;si seçebilirsin. Dosyalar sırayla işlenir ve her başarılı rapor kaydedilir.
        </p>
      </header>

      <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
        <div className="rounded-xl border border-emerald-200 bg-white p-5">
          <p className="text-sm font-semibold uppercase text-emerald-700">PDF Yükleme</p>
          <div className="mt-4 rounded-lg border border-dashed border-emerald-300 bg-emerald-50/40 p-4">
            <input
              type="file"
              accept="application/pdf,.pdf"
              multiple
              onChange={addFiles}
              className="block w-full text-sm text-slate-600"
            />

            <p className="mt-3 text-xs leading-5 text-slate-500">
              Aynı anda birden fazla PDF seçebilir veya tekrar dosya seçerek listeye yeni raporlar ekleyebilirsin.
            </p>

            {selectedFiles.length > 0 ? (
              <div className="mt-4 space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-slate-900">
                    Seçilen PDF&apos;ler ({selectedFiles.length})
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
                    Tümünü temizle
                  </button>
                </div>
                {selectedFiles.map((file) => (
                  <div
                    key={fileKey(file)}
                    className="flex items-center justify-between gap-3 rounded-lg border border-emerald-100 bg-white px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-900">{file.name}</p>
                      <p className="text-xs text-slate-500">{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeFile(file)}
                      disabled={isUploading}
                      className="shrink-0 rounded-md px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50"
                    >
                      Kaldır
                    </button>
                  </div>
                ))}
              </div>
            ) : null}

            <button
              type="button"
              onClick={handleUpload}
              disabled={isUploading || selectedFiles.length === 0}
              className="mt-4 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isUploading
                ? progress || 'PDF’ler analiz ediliyor...'
                : `${selectedFiles.length || ''} PDF’yi Yükle ve Analiz Et`.trim()}
            </button>
          </div>
        </div>
      </section>

      {uploadResults.length > 0 ? (
        <div className="space-y-2">
          {uploadResults.map((item) => (
            <div
              key={item.fileName}
              className={`rounded-xl border p-4 text-sm ${
                item.error
                  ? 'border-red-200 bg-red-50 text-red-800'
                  : 'border-emerald-200 bg-emerald-50 text-emerald-800'
              }`}
            >
              <strong>{item.fileName}</strong>
              <span className="ml-2">
                {item.error ? `— ${item.error}` : `— başarıyla analiz edildi (${item.result?.counts.total ?? 0} sonuç)`}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {backendError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{backendError}</div>
      ) : null}

      {backendResult ? (
        <section className="space-y-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Son başarıyla işlenen PDF&apos;nin analizi
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4"><p className="text-sm text-slate-500">Toplam Sonuç</p><p className="mt-2 text-2xl font-semibold">{backendResult.counts.total}</p></div>
            <div className="rounded-xl border border-red-200 bg-white p-4"><p className="text-sm text-slate-500">Yüksek</p><p className="mt-2 text-2xl font-semibold">{groupedResults.high.length}</p></div>
            <div className="rounded-xl border border-amber-200 bg-white p-4"><p className="text-sm text-slate-500">Düşük</p><p className="mt-2 text-2xl font-semibold">{groupedResults.low.length}</p></div>
            <div className="rounded-xl border border-violet-200 bg-white p-4"><p className="text-sm text-slate-500">Kontrol Gereken</p><p className="mt-2 text-2xl font-semibold">{groupedResults.review.length}</p></div>
          </div>

          <ResultGroup title="Yüksek Sonuçlar" description="Referans aralığının üzerindeki sonuçlar." results={groupedResults.high} tone="high" />
          <ResultGroup title="Düşük Sonuçlar" description="Referans aralığının altındaki sonuçlar." results={groupedResults.low} tone="low" />
          <ResultGroup title="Hekim Kontrolü Gerekenler" description="Belirsiz veya referans bilgisi yetersiz sonuçlar." results={groupedResults.review} tone="review" />
        </section>
      ) : null}
    </div>
  );
}
