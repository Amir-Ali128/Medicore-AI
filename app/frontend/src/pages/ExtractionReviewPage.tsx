import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import DoctorLanguageSummary from '../components/DoctorLanguageSummary';
import SectionCard from '../components/ui/SectionCard';
import { buildDoctorInterpretation } from '../services/clinicalInterpreter';
import {
  getAnalysisRunResults,
  LAST_ANALYSIS_RUN_ID_KEY,
  type LabAnalysisResult,
  type LabResultStatus,
} from '../services/labAnalysisClient';

const STATUS_LABELS: Record<string, string> = {
  normal: 'Normal',
  low: 'Düşük',
  high: 'Yüksek',
  unknown: 'Belirsiz',
  needs_review: 'Hekim kontrolü gerekli',
  ready: 'Değerlendirmeye hazır',
  completed: 'Tamamlandı',
  waiting: 'Sonuç bekleniyor',
};

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status.replace(/_/g, ' ');
}

function statusClassName(status: string) {
  switch (status) {
    case 'normal':
    case 'ready':
    case 'completed':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700';
    case 'low':
    case 'high':
      return 'border-red-200 bg-red-50 text-red-700';
    case 'needs_review':
    case 'pending':
    case 'pending_review':
      return 'border-amber-200 bg-amber-50 text-amber-700';
    case 'unknown':
    case 'waiting':
      return 'border-slate-200 bg-slate-50 text-slate-700';
    default:
      return 'border-blue-200 bg-blue-50 text-blue-700';
  }
}

function StatusPill({ status }: { status: LabResultStatus | string }) {
  return (
    <span
      className={`inline-flex w-fit rounded-full border px-2.5 py-1 text-xs font-semibold ${statusClassName(
        status,
      )}`}
    >
      {statusLabel(status)}
    </span>
  );
}

function formatReference(result: LabAnalysisResult) {
  if (result.reference_min === null && result.reference_max === null) {
    return 'Referans aralığı doğrulanmalı';
  }

  return `${result.reference_min ?? '-'} – ${result.reference_max ?? '-'} ${
    result.unit
  }`;
}

function formatConfidence(value: number) {
  if (!Number.isFinite(value)) return '-';
  const percent = value <= 1 ? value * 100 : value;
  return `%${Math.round(percent)}`;
}

function resultReviewStatus(result: LabAnalysisResult) {
  if (result.needs_review || result.result_status === 'needs_review') {
    return 'needs_review';
  }
  if (result.result_status === 'unknown') return 'unknown';
  return 'ready';
}

export default function ExtractionReviewPage() {
  const [analysisRunId, setAnalysisRunId] = useState<string | null>(null);
  const [results, setResults] = useState<LabAnalysisResult[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const storedAnalysisRunId = localStorage.getItem(LAST_ANALYSIS_RUN_ID_KEY);
    setAnalysisRunId(storedAnalysisRunId);

    if (!storedAnalysisRunId) {
      setIsLoading(false);
      return;
    }

    const currentAnalysisRunId = storedAnalysisRunId;

    async function loadResults() {
      try {
        setIsLoading(true);
        setError('');
        setResults(await getAnalysisRunResults(currentAnalysisRunId));
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Son analiz sonuçları yüklenemedi.',
        );
      } finally {
        setIsLoading(false);
      }
    }

    void loadResults();
  }, []);

  const summary = useMemo(() => {
    const needsReview = results.filter(
      (result) =>
        result.needs_review || result.result_status === 'needs_review',
    ).length;
    const abnormal = results.filter(
      (result) => result.result_status === 'low' || result.result_status === 'high',
    ).length;
    const unknown = results.filter(
      (result) => result.result_status === 'unknown',
    ).length;

    return {
      total: results.length,
      abnormal,
      needsReview,
      unknown,
      ready: results.length - needsReview - unknown,
    };
  }, [results]);

  const overallStatus =
    summary.total === 0
      ? 'waiting'
      : summary.needsReview > 0 || summary.unknown > 0
        ? 'needs_review'
        : 'completed';

  const doctorInterpretation = useMemo(
    () => buildDoctorInterpretation(results),
    [results],
  );

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase text-cyan-700">
            Sonuç değerlendirme
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950">
            Klinik bilgiler ve test sonuçları
          </h1>
          <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-500">
            Son laboratuvar analizindeki değerleri, referans aralıklarını ve hekim
            kontrolü gerektiren sonuçları tek ekranda inceleyin.
          </p>
          <p className="mt-3 inline-flex rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-800">
            Bu ekran kesin tanı üretmez; sonuçlar hastanın klinik bilgileriyle birlikte
            hekim tarafından değerlendirilmelidir.
          </p>
        </div>

        <Link
          to="/timeline"
          className="inline-flex shrink-0 items-center justify-center rounded-lg border border-blue-200 bg-white px-4 py-2.5 text-sm font-semibold text-blue-700 transition hover:bg-blue-50"
        >
          Geçmiş sonuçları göster
        </Link>
      </header>

      {!analysisRunId && !isLoading ? (
        <SectionCard
          title="Henüz analiz sonucu bulunmuyor"
          description="Bu ekranı kullanmadan önce laboratuvar raporu yükleyin veya manuel sonuç girin."
        >
          <Link
            to="/analysis/mock"
            className="inline-flex rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
          >
            Laboratuvar analizine git
          </Link>
        </SectionCard>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      {isLoading ? (
        <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-600">
          Son analiz sonuçları yükleniyor…
        </div>
      ) : null}

      {analysisRunId && !isLoading ? (
        <>
          <SectionCard
            title="Son laboratuvar analizinin özeti"
            description="Mevcut analizde bulunan normal, anormal ve kontrol gerektiren sonuçların dağılımı."
          >
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
              {[
                ['Toplam test', summary.total],
                ['Düşük / yüksek', summary.abnormal],
                ['Hekim kontrolü', summary.needsReview],
                ['Belirsiz', summary.unknown],
                ['Hazır sonuç', summary.ready],
              ].map(([label, value]) => (
                <div
                  key={String(label)}
                  className="rounded-lg border border-slate-200 bg-slate-50 p-4"
                >
                  <p className="text-sm text-slate-600">{label}</p>
                  <p className="mt-2 text-3xl font-semibold text-slate-950">
                    {value}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-5 flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white p-4">
              <span className="text-sm font-medium text-slate-700">
                Genel değerlendirme durumu:
              </span>
              <StatusPill status={overallStatus} />
            </div>
          </SectionCard>

          <SectionCard
            title="Sonuçların klinik özeti"
            description="Düşük ve yüksek sonuçlardan oluşturulan, hekim incelemesine yardımcı açıklama."
          >
            <DoctorLanguageSummary summary={doctorInterpretation} />
          </SectionCard>

          <SectionCard
            title="Test sonuçları"
            description="Test adı, ölçülen değer, referans aralığı ve kontrol durumu."
          >
            {results.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
                Bu analiz için kullanılabilir test sonucu bulunamadı.
              </div>
            ) : (
              <div className="overflow-hidden rounded-lg border border-slate-200">
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-slate-200">
                    <thead className="bg-slate-50">
                      <tr>
                        {[
                          'Test',
                          'Sonuç',
                          'Referans aralığı',
                          'Eşleşme güveni',
                          'Kontrol durumu',
                          'Açıklama',
                        ].map((heading) => (
                          <th
                            key={heading}
                            className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500"
                          >
                            {heading}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 bg-white">
                      {results.map((result) => (
                        <tr key={result.lab_result_id}>
                          <td className="px-4 py-4 font-medium text-slate-950">
                            {result.canonical_name ?? result.raw_parameter_name}
                          </td>
                          <td className="px-4 py-4 text-slate-700">
                            {result.normalized_value} {result.unit}
                          </td>
                          <td className="px-4 py-4 text-slate-600">
                            {formatReference(result)}
                          </td>
                          <td className="px-4 py-4 text-slate-600">
                            {formatConfidence(result.alias_confidence)}
                          </td>
                          <td className="px-4 py-4">
                            <StatusPill status={resultReviewStatus(result)} />
                          </td>
                          <td className="min-w-64 px-4 py-4 text-slate-600">
                            {result.reason}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </SectionCard>

          <SectionCard
            title="İlgili işlemler"
            description="Sonuçları ayrıntılı inceleyin, klinik yorumlara geçin veya önceki kayıtları açın."
          >
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {[
                ['Ayrıntılı sonuçları aç', '/analysis/results'],
                ['Klinik yorumları aç', '/clinical-hypotheses'],
                ['Hekim onayına git', '/doctor-review'],
                ['Geçmiş sonuçları göster', '/timeline'],
                ['Yeni laboratuvar analizi', '/analysis/mock'],
              ].map(([label, to]) => (
                <Link
                  key={to}
                  to={to}
                  className="rounded-lg border border-slate-200 bg-white p-4 font-semibold text-slate-900 transition hover:border-blue-200 hover:bg-blue-50"
                >
                  {label}
                </Link>
              ))}
            </div>
          </SectionCard>
        </>
      ) : null}
    </div>
  );
}
