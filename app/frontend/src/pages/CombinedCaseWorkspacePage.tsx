import { useState, type ChangeEvent } from 'react';
import { Link } from 'react-router-dom';

import SectionCard from '../components/ui/SectionCard';
import {
  uploadCombinedCasePdf,
  type CombinedCaseImportResponse,
} from '../services/combinedCaseClient';
import MockAnalysisPage from './MockAnalysisPage';

type UploadResult = {
  fileName: string;
  result?: CombinedCaseImportResponse;
  error?: string;
};

function fileKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

export default function CombinedCaseWorkspacePage() {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadResults, setUploadResults] = useState<UploadResult[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');

  function addFiles(event: ChangeEvent<HTMLInputElement>) {
    const incoming = Array.from(event.target.files ?? []).filter((file) =>
      file.name.toLowerCase().endsWith('.pdf'),
    );

    if (incoming.length === 0) {
      event.target.value = '';
      return;
    }

    setSelectedFiles((current) => {
      const existing = new Set(current.map(fileKey));
      const uniqueIncoming = incoming.filter((file) => !existing.has(fileKey(file)));
      return [...current, ...uniqueIncoming];
    });
    setError('');
    setUploadResults([]);
    event.target.value = '';
  }

  function removeFile(file: File) {
    setSelectedFiles((current) =>
      current.filter((item) => fileKey(item) !== fileKey(file)),
    );
    setUploadResults([]);
    setError('');
  }

  async function handleUpload() {
    if (selectedFiles.length === 0) {
      setError('Önce en az bir PDF dosyası seçmelisin.');
      return;
    }

    setBusy(true);
    setError('');
    setUploadResults([]);

    const nextResults: UploadResult[] = [];

    for (let index = 0; index < selectedFiles.length; index += 1) {
      const file = selectedFiles[index];
      setProgress(`${index + 1}/${selectedFiles.length} · ${file.name} işleniyor`);

      try {
        const result = await uploadCombinedCasePdf(file);
        nextResults.push({ fileName: file.name, result });
      } catch (uploadError) {
        nextResults.push({
          fileName: file.name,
          error:
            uploadError instanceof Error
              ? uploadError.message
              : 'PDF aktarımı başarısız.',
        });
      }

      setUploadResults([...nextResults]);
    }

    setProgress('');
    setBusy(false);

    if (nextResults.every((item) => item.error)) {
      setError('Seçilen PDF dosyalarının hiçbiri işlenemedi. Aşağıdaki dosya hatalarını kontrol et.');
    }
  }

  const successfulResults = uploadResults.filter(
    (item): item is UploadResult & { result: CombinedCaseImportResponse } =>
      Boolean(item.result),
  );
  const latestResult =
    successfulResults.length > 0
      ? successfulResults[successfulResults.length - 1].result
      : null;
  const patient = latestResult?.clinical_context.patient_information;

  return (
    <div className="space-y-8">
      <SectionCard
        title="Birden fazla PDF ile vaka aktarımı"
        description="İstediğin kadar PDF ekleyebilirsin. Her PDF sırayla ayrıştırılır; hasta bilgileri, kan tahlilleri ve radyoloji verileri ilgili modüllere kaydedilir."
      >
        <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
          <div>
            <div className="rounded-xl border border-dashed border-blue-300 bg-blue-50/50 p-5">
              <input
                type="file"
                accept="application/pdf,.pdf"
                multiple
                onChange={addFiles}
                className="block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-700 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-blue-800"
              />

              <p className="mt-3 text-xs leading-5 text-slate-500">
                Aynı anda birden fazla dosya seçebilir veya tekrar “Dosya Seç” diyerek listeye yeni PDF'ler ekleyebilirsin.
              </p>

              {selectedFiles.length > 0 ? (
                <div className="mt-4 space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-slate-900">
                      Seçilen PDF'ler ({selectedFiles.length})
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedFiles([]);
                        setUploadResults([]);
                        setError('');
                      }}
                      disabled={busy}
                      className="text-xs font-semibold text-slate-500 hover:text-red-600 disabled:opacity-50"
                    >
                      Tümünü temizle
                    </button>
                  </div>

                  <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
                    {selectedFiles.map((file) => (
                      <div
                        key={fileKey(file)}
                        className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2"
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
                          disabled={busy}
                          className="shrink-0 rounded-md px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50"
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
                disabled={busy || selectedFiles.length === 0}
                className="mt-4 rounded-lg bg-blue-700 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy
                  ? progress || 'PDF’ler işleniyor…'
                  : `${selectedFiles.length || ''} PDF’yi İşle ve Kaydet`.trim()}
              </button>
            </div>

            {error ? (
              <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800">
                {error}
              </div>
            ) : null}

            {uploadResults.length > 0 ? (
              <div className="mt-4 space-y-2">
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
                      {item.error ? `— ${item.error}` : '— başarıyla işlendi ve kaydedildi'}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
            <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">
              PDF başlık düzeni
            </p>
            <ol className="mt-3 space-y-3 text-sm text-slate-700">
              <li>
                <strong>1. HASTA BİLGİLERİ VE KLİNİK BULGULAR</strong>
              </li>
              <li>
                <strong>2. KAN TAHLİLLERİ</strong>
              </li>
              <li>
                <strong>3. RADYOLOJİ RAPORU</strong>
              </li>
            </ol>
            <p className="mt-4 text-xs leading-5 text-slate-500">
              Her PDF şu an ayrı işlenir. Başlıkların PDF’de ayrı satırda olması gerekir. Kan sonuçlarında test adı, değer, birim ve referans aynı satırda bulunmalıdır.
            </p>
          </div>
        </div>

        {latestResult ? (
          <div className="mt-6 space-y-4">
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
              <h3 className="font-semibold text-emerald-950">
                {successfulResults.length} PDF başarıyla işlendi
              </h3>
              <p className="mt-2 text-sm text-emerald-900">
                Son işlenen kayıt: {patient?.full_name || 'Hasta adı bulunamadı'}
                {patient?.age !== null && patient?.age !== undefined
                  ? ` · ${patient.age} yaş`
                  : ''}
                {patient?.sex ? ` · ${patient.sex}` : ''}
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-sm font-semibold text-slate-950">Klinik bölüm</p>
                <p className="mt-2 text-2xl font-semibold text-blue-700">
                  {latestResult.sections.clinical_characters}
                </p>
                <p className="text-xs text-slate-500">karakter ayrıldı</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-sm font-semibold text-slate-950">Kan tahlilleri</p>
                <p className="mt-2 text-2xl font-semibold text-emerald-700">
                  {latestResult.sections.parsed_lab_values}
                </p>
                <p className="text-xs text-slate-500">sonuç parse edildi</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-sm font-semibold text-slate-950">Radyoloji</p>
                <p className="mt-2 text-2xl font-semibold text-violet-700">
                  {latestResult.radiology_report.modality}
                </p>
                <p className="text-xs text-slate-500">
                  {latestResult.radiology_report.body_part}
                </p>
              </div>
            </div>

            {latestResult.warnings.length > 0 ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                <p className="text-sm font-semibold text-amber-950">Son PDF için kontrol notları</p>
                <ul className="mt-2 space-y-1 text-sm text-amber-900">
                  {latestResult.warnings.map((warning: string) => (
                    <li key={warning}>• {warning}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div className="flex flex-wrap gap-3">
              <Link
                to="/analysis/results"
                className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800"
              >
                Kan sonucunu ayrı değerlendir
              </Link>
              <Link
                to="/radiology"
                className="rounded-lg bg-violet-700 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-800"
              >
                Radyolojiyi ayrı değerlendir
              </Link>
              <Link
                to="/combined-evaluation"
                className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800"
              >
                Üç veriyi birlikte değerlendir
              </Link>
            </div>
          </div>
        ) : null}
      </SectionCard>

      <MockAnalysisPage />
    </div>
  );
}
