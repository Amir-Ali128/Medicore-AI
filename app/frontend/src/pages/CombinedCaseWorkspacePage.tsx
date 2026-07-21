import { useState, type ChangeEvent } from 'react';
import { Link } from 'react-router-dom';

import SectionCard from '../components/ui/SectionCard';
import {
  uploadCombinedCasePdf,
  type CombinedCaseImportResponse,
} from '../services/combinedCaseClient';
import MockAnalysisPage from './MockAnalysisPage';

export default function CombinedCaseWorkspacePage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [result, setResult] = useState<CombinedCaseImportResponse | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleUpload() {
    if (!selectedFile) {
      setError('Önce üç bölümlü PDF dosyasını seçmelisin.');
      return;
    }

    try {
      setBusy(true);
      setError('');
      setResult(await uploadCombinedCasePdf(selectedFile));
    } catch (uploadError) {
      setResult(null);
      setError(
        uploadError instanceof Error
          ? uploadError.message
          : 'Birleşik vaka PDF aktarımı başarısız.',
      );
    } finally {
      setBusy(false);
    }
  }

  const patient = result?.clinical_context.patient_information;

  return (
    <div className="space-y-8">
      <SectionCard
        title="Tek PDF’den üç bölümlü vaka aktarımı"
        description="Hasta bilgileri ve klinik bulgular, kan tahlilleri ve radyoloji raporu aynı PDF’den ayrılarak ilgili modüllere kaydedilir."
      >
        <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
          <div>
            <div className="rounded-xl border border-dashed border-blue-300 bg-blue-50/50 p-5">
              <input
                type="file"
                accept="application/pdf,.pdf"
                onChange={(event: ChangeEvent<HTMLInputElement>) => {
                  setSelectedFile(event.target.files?.[0] ?? null);
                  setError('');
                  setResult(null);
                }}
                className="block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-700 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-blue-800"
              />
              {selectedFile ? (
                <p className="mt-3 text-sm text-slate-700">
                  Seçilen dosya:{' '}
                  <strong className="text-slate-950">{selectedFile.name}</strong>
                </p>
              ) : null}
              <button
                type="button"
                onClick={handleUpload}
                disabled={busy || !selectedFile}
                className="mt-4 rounded-lg bg-blue-700 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy ? 'PDF üç bölüme ayrılıyor…' : 'PDF’yi Ayır ve Kaydet'}
              </button>
            </div>

            {error ? (
              <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800">
                {error}
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
              Başlıkların her biri PDF’de ayrı satırda olmalıdır. Kan sonuçlarında
              test adı, değer, birim ve referans aynı satırda bulunmalıdır.
            </p>
          </div>
        </div>

        {result ? (
          <div className="mt-6 space-y-4">
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
              <h3 className="font-semibold text-emerald-950">
                Üç bölüm başarıyla ayrıldı ve kaydedildi
              </h3>
              <p className="mt-2 text-sm text-emerald-900">
                {patient?.full_name || 'Hasta adı bulunamadı'}
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
                  {result.sections.clinical_characters}
                </p>
                <p className="text-xs text-slate-500">karakter ayrıldı</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-sm font-semibold text-slate-950">Kan tahlilleri</p>
                <p className="mt-2 text-2xl font-semibold text-emerald-700">
                  {result.sections.parsed_lab_values}
                </p>
                <p className="text-xs text-slate-500">sonuç parse edildi</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-sm font-semibold text-slate-950">Radyoloji</p>
                <p className="mt-2 text-2xl font-semibold text-violet-700">
                  {result.radiology_report.modality}
                </p>
                <p className="text-xs text-slate-500">
                  {result.radiology_report.body_part}
                </p>
              </div>
            </div>

            {result.warnings.length > 0 ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                <p className="text-sm font-semibold text-amber-950">Kontrol notları</p>
                <ul className="mt-2 space-y-1 text-sm text-amber-900">
                  {result.warnings.map((warning) => (
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
                Kan sonuçlarını aç
              </Link>
              <Link
                to="/radiology"
                className="rounded-lg bg-violet-700 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-800"
              >
                Birleşik değerlendirmeyi aç
              </Link>
            </div>
          </div>
        ) : null}
      </SectionCard>

      <MockAnalysisPage />
    </div>
  );
}
