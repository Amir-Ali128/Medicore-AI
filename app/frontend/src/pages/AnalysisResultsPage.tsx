import { useEffect, useMemo, useState, type ComponentProps } from 'react';

import EmptyState from '../components/ui/EmptyState';
import ErrorState from '../components/ui/ErrorState';
import LoadingState from '../components/ui/LoadingState';
import SectionCard from '../components/ui/SectionCard';
import StatusBadge from '../components/ui/StatusBadge';
import {
  getAnalysisRunResults,
  type ClinicalIntakeInput,
  type LabAnalysisResult,
} from '../services/labAnalysisClient';

const ACTIVE_CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';

type BadgeStatus = ComponentProps<typeof StatusBadge>['status'];
type ResultTone = 'high' | 'low' | 'review';

type ClinicalSummaryItem = {
  label: string;
  value: string;
};

function readClinicalIntake(): ClinicalIntakeInput | null {
  try {
    const raw = localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY);
    return raw ? (JSON.parse(raw) as ClinicalIntakeInput) : null;
  } catch {
    return null;
  }
}

function textValue(value: string | number | null | undefined) {
  if (value === null || value === undefined) return null;
  const normalized = String(value).trim();
  return normalized || null;
}

function sexLabel(value: string | null | undefined) {
  const labels: Record<string, string> = {
    male: 'Erkek',
    female: 'Kadın',
    other: 'Diğer',
    unknown: 'Bilinmiyor',
  };
  return value ? labels[value] ?? value : null;
}

function buildClinicalSummary(
  clinicalIntake: ClinicalIntakeInput | null,
): ClinicalSummaryItem[] {
  if (!clinicalIntake) return [];

  const patient = clinicalIntake.patient_information;
  const complaint = clinicalIntake.presenting_complaint;
  const history = clinicalIntake.clinical_history_details;
  const exam = clinicalIntake.physical_exam;

  const bloodPressure =
    exam.blood_pressure_systolic !== null ||
    exam.blood_pressure_diastolic !== null
      ? `${exam.blood_pressure_systolic ?? '-'} / ${exam.blood_pressure_diastolic ?? '-'} mmHg`
      : null;

  const items: Array<ClinicalSummaryItem | null> = [
    textValue(patient.full_name)
      ? { label: 'Hasta', value: textValue(patient.full_name)! }
      : null,
    textValue(patient.age)
      ? { label: 'Yaş', value: `${textValue(patient.age)} yaş` }
      : null,
    sexLabel(patient.sex)
      ? { label: 'Cinsiyet', value: sexLabel(patient.sex)! }
      : null,
    textValue(complaint.chief_complaint)
      ? { label: 'Ana şikâyet', value: textValue(complaint.chief_complaint)! }
      : null,
    textValue(complaint.complaint_duration)
      ? { label: 'Şikâyetin süresi', value: textValue(complaint.complaint_duration)! }
      : null,
    textValue(complaint.associated_symptoms)
      ? {
          label: 'Eşlik eden belirtiler',
          value: textValue(complaint.associated_symptoms)!,
        }
      : null,
    textValue(history.history_of_present_illness)
      ? {
          label: 'Şikâyetin öyküsü',
          value: textValue(history.history_of_present_illness)!,
        }
      : null,
    textValue(history.past_medical_history)
      ? {
          label: 'Geçmiş sağlık öyküsü',
          value: textValue(history.past_medical_history)!,
        }
      : null,
    textValue(history.family_history)
      ? { label: 'Aile öyküsü', value: textValue(history.family_history)! }
      : null,
    textValue(history.medications)
      ? { label: 'Kullanılan ilaçlar', value: textValue(history.medications)! }
      : null,
    textValue(history.allergies)
      ? { label: 'Alerjiler', value: textValue(history.allergies)! }
      : null,
    bloodPressure ? { label: 'Tansiyon', value: bloodPressure } : null,
    textValue(exam.pulse_bpm)
      ? { label: 'Nabız', value: `${textValue(exam.pulse_bpm)} /dk` }
      : null,
    textValue(exam.temperature_c)
      ? { label: 'Vücut sıcaklığı', value: `${textValue(exam.temperature_c)} °C` }
      : null,
    textValue(exam.respiratory_rate)
      ? {
          label: 'Solunum sayısı',
          value: `${textValue(exam.respiratory_rate)} /dk`,
        }
      : null,
    textValue(exam.oxygen_saturation_percent)
      ? {
          label: 'Oksijen satürasyonu',
          value: `%${textValue(exam.oxygen_saturation_percent)}`,
        }
      : null,
    textValue(exam.examination_findings)
      ? {
          label: 'Muayene bulguları',
          value: textValue(exam.examination_findings)!,
        }
      : null,
  ];

  return items.filter((item): item is ClinicalSummaryItem => item !== null);
}

function toDisplayStatus(status: LabAnalysisResult['result_status']): BadgeStatus {
  if (status === 'low') return 'LOW' as BadgeStatus;
  if (status === 'high') return 'HIGH' as BadgeStatus;
  return 'PENDING' as BadgeStatus;
}

function formatReferenceRange(result: LabAnalysisResult) {
  if (result.reference_min === null && result.reference_max === null) return '-';
  return `${result.reference_min ?? '-'} - ${result.reference_max ?? '-'} ${result.unit ?? ''}`;
}

function ResultTable({
  title,
  results,
  tone,
}: {
  title: string;
  results: LabAnalysisResult[];
  tone: ResultTone;
}) {
  if (results.length === 0) return null;

  const headerClass =
    tone === 'high'
      ? 'bg-rose-50 text-rose-800'
      : tone === 'low'
        ? 'bg-amber-50 text-amber-800'
        : 'bg-violet-50 text-violet-800';

  return (
    <section className="overflow-hidden rounded-xl border border-slate-200">
      <div
        className={`flex items-center justify-between gap-3 px-4 py-3 ${headerClass}`}
      >
        <h3 className="font-semibold">{title}</h3>
        <span className="text-sm font-semibold">{results.length} sonuç</span>
      </div>

      <div className="overflow-x-auto bg-white">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              {['Test', 'Ölçülen değer', 'Referans aralığı', 'Durum', 'Değerlendirme notu'].map(
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
          <tbody className="divide-y divide-slate-200">
            {results.map((result) => (
              <tr key={result.lab_result_id} className="bg-white">
                <td className="px-4 py-4 font-medium text-slate-950">
                  {result.canonical_name ?? result.raw_parameter_name}
                </td>
                <td className="whitespace-nowrap px-4 py-4 text-slate-600">
                  {result.normalized_value} {result.unit}
                </td>
                <td className="whitespace-nowrap px-4 py-4 text-slate-600">
                  {formatReferenceRange(result)}
                </td>
                <td className="px-4 py-4">
                  <StatusBadge status={toDisplayStatus(result.result_status)} />
                </td>
                <td className="min-w-64 px-4 py-4 text-sm leading-6 text-slate-600">
                  {result.reason || 'Sonuç hekim değerlendirmesi için hazırlanmıştır.'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function AnalysisResultsPage() {
  const [results, setResults] = useState<LabAnalysisResult[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [clinicalIntake] = useState<ClinicalIntakeInput | null>(readClinicalIntake);

  const analysisRunId = localStorage.getItem('medicore:lastAnalysisRunId');

  useEffect(() => {
    async function loadResults() {
      try {
        setIsLoading(true);
        setError('');
        if (!analysisRunId) {
          setResults([]);
          return;
        }
        setResults(await getAnalysisRunResults(analysisRunId));
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Analiz sonuçları yüklenemedi.',
        );
      } finally {
        setIsLoading(false);
      }
    }
    void loadResults();
  }, [analysisRunId]);

  const clinicalSummary = useMemo(
    () => buildClinicalSummary(clinicalIntake),
    [clinicalIntake],
  );

  const groupedResults = useMemo(
    () => ({
      high: results.filter((result) => result.result_status === 'high'),
      low: results.filter((result) => result.result_status === 'low'),
      review: results.filter(
        (result) =>
          result.result_status === 'needs_review' ||
          result.result_status === 'unknown',
      ),
    }),
    [results],
  );

  const visibleResults = useMemo(
    () => [
      ...groupedResults.high,
      ...groupedResults.low,
      ...groupedResults.review,
    ],
    [groupedResults],
  );

  if (isLoading) {
    return (
      <LoadingState
        title="Analiz sonuçları yükleniyor"
        description="Laboratuvar sonuçları sistemden alınıyor."
      />
    );
  }

  if (error) {
    return <ErrorState title="Analiz sonuçları yüklenemedi" description={error} />;
  }

  if (!analysisRunId || results.length === 0) {
    return (
      <EmptyState
        title="Henüz analiz sonucu bulunmuyor"
        description="Önce PDF yükleyin veya manuel laboratuvar sonucu girin."
        actionLabel="Laboratuvar analizine git"
        to="/analysis/mock"
      />
    );
  }

  const summaryCards = [
    ['İşlenen sonuçlar', results.length],
    ['Yüksek sonuçlar', groupedResults.high.length],
    ['Düşük sonuçlar', groupedResults.low.length],
    ['Hekim kontrolü gerekenler', groupedResults.review.length],
  ] as const;

  return (
    <div className="space-y-8">
      <header>
        <p className="text-sm font-semibold uppercase text-cyan-700">
          Hasta raporu
        </p>
        <h2 className="mt-2 text-3xl font-semibold text-slate-950">
          Klinik ve laboratuvar değerlendirmesi
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          Klinik bilgiler ve laboratuvar sonuçları aynı raporda birlikte gösterilir.
        </p>
      </header>

      {clinicalSummary.length > 0 ? (
        <SectionCard
          title="Klinik bilgiler"
          description="Hasta kaydında girilen şikâyet, öykü, muayene ve yaşamsal bulgular."
        >
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {clinicalSummary.map((item) => (
              <div
                key={item.label}
                className="rounded-lg border border-slate-200 bg-slate-50 p-4"
              >
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {item.label}
                </p>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-800">
                  {item.value}
                </p>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : (
        <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5 text-sm text-slate-600">
          Bu rapor için klinik bilgi bulunmuyor. Hasta Kaydı bölümünden şikâyet, öykü ve muayene bilgileri eklenebilir.
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map(([title, value]) => (
          <div
            key={title}
            className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
          >
            <p className="text-sm font-medium text-slate-600">{title}</p>
            <p className="mt-3 text-3xl font-semibold text-slate-950">{value}</p>
          </div>
        ))}
      </div>

      <SectionCard title="Laboratuvar değerlendirmesi" description="">
        {visibleResults.length === 0 ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-6 text-sm text-emerald-800">
            Anormal veya hekim kontrolü gerektiren sonuç bulunmadı.
          </div>
        ) : (
          <div className="space-y-5">
            <ResultTable
              title="Yüksek sonuçlar"
              results={groupedResults.high}
              tone="high"
            />
            <ResultTable
              title="Düşük sonuçlar"
              results={groupedResults.low}
              tone="low"
            />
            <ResultTable
              title="Hekim kontrolü gerekenler"
              results={groupedResults.review}
              tone="review"
            />
          </div>
        )}
      </SectionCard>
    </div>
  );
}
