import { useMemo, useState, type ChangeEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import ClaudeEvaluationCard from '../components/clinical/ClaudeEvaluationCard';
import ClinicalIntakeForm, {
  createEmptyClinicalIntake,
} from '../components/clinical/ClinicalIntakeForm';
import SectionCard from '../components/ui/SectionCard';
import {
  evaluateClaudeAbnormalResults,
  type ClaudeReviewGenerationResult,
} from '../services/claudeReviewClient';
import {
  runBackendMockAnalysis,
  submitManualLabResults,
  uploadLabReportPdf,
  type LabAnalysisResponse,
  type LabAnalysisResult,
  type LabResultStatus,
  type ManualLabValueInput,
} from '../services/labAnalysisClient';

type ManualRow = {
  id: string;
  parameterName: string;
  value: string;
  unit: string;
  referenceMin: string;
  referenceMax: string;
  measuredAt: string;
};

type ManualField = {
  key: keyof Omit<ManualRow, 'id'>;
  label: string;
  placeholder?: string;
  type?: 'text' | 'date';
  inputMode?: 'text' | 'decimal';
  wide?: boolean;
};

type ResultTone = 'low' | 'high' | 'review';

const MANUAL_FIELDS: ManualField[] = [
  {
    key: 'parameterName',
    label: 'Test adı',
    placeholder: 'Hemoglobin',
    wide: true,
  },
  {
    key: 'value',
    label: 'Sonuç',
    placeholder: '13.8',
    inputMode: 'decimal',
  },
  { key: 'unit', label: 'Birim', placeholder: 'g/dL' },
  {
    key: 'referenceMin',
    label: 'Referans minimum',
    placeholder: '12',
    inputMode: 'decimal',
  },
  {
    key: 'referenceMax',
    label: 'Referans maksimum',
    placeholder: '16',
    inputMode: 'decimal',
  },
  {
    key: 'measuredAt',
    label: 'Ölçüm tarihi',
    type: 'date',
    wide: true,
  },
];

function todayValue() {
  return new Date().toISOString().slice(0, 10);
}

function createManualRow(): ManualRow {
  return {
    id: crypto.randomUUID(),
    parameterName: '',
    value: '',
    unit: '',
    referenceMin: '',
    referenceMax: '',
    measuredAt: todayValue(),
  };
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
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${statusClassName(
        status,
      )}`}
    >
      {statusLabel(status)}
    </span>
  );
}

function formatReference(result: LabAnalysisResult) {
  if (result.reference_min === null && result.reference_max === null) {
    return 'Hekim kontrolü gerekli';
  }

  return `${result.reference_min ?? '-'} - ${result.reference_max ?? '-'} ${
    result.unit ?? ''
  }`;
}

function parseOptionalNumber(value: string): number | null {
  if (!value.trim()) return null;

  const parsed = Number(value.replace(',', '.'));
  if (!Number.isFinite(parsed)) {
    throw new Error(`"${value}" geçerli bir sayı değil.`);
  }

  return parsed;
}

function toManualValue(row: ManualRow): ManualLabValueInput {
  const parameterName = row.parameterName.trim();
  const unit = row.unit.trim();

  if (!parameterName) {
    throw new Error('Her manuel sonuç için test adı gerekli.');
  }

  if (!row.value.trim()) {
    throw new Error(`${parameterName}: sonuç değeri gerekli.`);
  }

  const normalizedValue = Number(row.value.replace(',', '.'));
  if (!Number.isFinite(normalizedValue)) {
    throw new Error(`${parameterName}: sonuç sayısal olmalı.`);
  }

  if (!unit) {
    throw new Error(`${parameterName}: birim gerekli.`);
  }

  const referenceMin = parseOptionalNumber(row.referenceMin);
  const referenceMax = parseOptionalNumber(row.referenceMax);

  if (
    referenceMin !== null &&
    referenceMax !== null &&
    referenceMin > referenceMax
  ) {
    throw new Error(
      `${parameterName}: minimum referans maksimumdan büyük olamaz.`,
    );
  }

  return {
    raw_parameter_name: parameterName,
    normalized_value: normalizedValue,
    unit,
    extracted_reference_min: referenceMin,
    extracted_reference_max: referenceMax,
    measured_at: row.measuredAt || null,
  };
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
  const navigate = useNavigate();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [manualReportDate, setManualReportDate] = useState(todayValue());
  const [clinicalIntake, setClinicalIntake] = useState(
    createEmptyClinicalIntake(),
  );
  const [manualRows, setManualRows] = useState<ManualRow[]>([
    createManualRow(),
  ]);
  const [backendResult, setBackendResult] =
    useState<LabAnalysisResponse | null>(null);
  const [backendError, setBackendError] = useState('');
  const [busyAction, setBusyAction] = useState<
    'sample' | 'pdf' | 'manual' | null
  >(null);
  const [isClaudeEvaluating, setIsClaudeEvaluating] = useState(false);
  const [claudeResult, setClaudeResult] =
    useState<ClaudeReviewGenerationResult | null>(null);
  const [claudeError, setClaudeError] = useState('');

  const groupedResults = useMemo(() => {
    const results = backendResult?.results ?? [];

    return {
      high: results.filter((item) => item.result_status === 'high'),
      low: results.filter((item) => item.result_status === 'low'),
      review: results.filter(
        (item) =>
          item.result_status === 'needs_review' ||
          item.result_status === 'unknown',
      ),
    };
  }, [backendResult]);

  const visibleResults = useMemo(
    () => [
      ...groupedResults.high,
      ...groupedResults.low,
      ...groupedResults.review,
    ],
    [groupedResults],
  );

  const summaryCards = [
    [
      'Processed results',
      backendResult?.counts.total ?? 0,
      'All values processed by the deterministic pipeline.',
    ],
    [
      'High signals',
      groupedResults.high.length,
      'Above an available reference range.',
    ],
    [
      'Low signals',
      groupedResults.low.length,
      'Below an available reference range.',
    ],
    [
      'Hekim Kontrolü Gerekenler',
      groupedResults.review.length,
      'Unknown or uncertain results separated for review.',
    ],
  ] as const;

  function acceptResult(result: LabAnalysisResponse) {
    setBackendResult(result);
    setClaudeResult(null);
    setClaudeError('');
  }

  function updateManualRow(
    rowId: string,
    field: keyof Omit<ManualRow, 'id'>,
    value: string,
  ) {
    setManualRows((rows) =>
      rows.map((row) => (row.id === rowId ? { ...row, [field]: value } : row)),
    );
  }

  function removeManualRow(rowId: string) {
    setManualRows((rows) =>
      rows.length === 1
        ? [createManualRow()]
        : rows.filter((row) => row.id !== rowId),
    );
  }

  async function runAction(action: 'sample' | 'pdf' | 'manual') {
    try {
      setBusyAction(action);
      setBackendError('');

      if (action === 'sample') {
        acceptResult(await runBackendMockAnalysis());
        return;
      }

      if (action === 'pdf') {
        if (!selectedFile) {
          throw new Error('Önce bir PDF dosyası seçmelisin.');
        }

        acceptResult(await uploadLabReportPdf(selectedFile, clinicalIntake));
        return;
      }

      if (!manualReportDate) {
        throw new Error('Manuel giriş için rapor tarihi gerekli.');
      }

      acceptResult(
        await submitManualLabResults({
          report_date: manualReportDate,
          clinical_context: clinicalIntake,
          values: manualRows.map(toManualValue),
        }),
      );
    } catch (error) {
      setBackendError(error instanceof Error ? error.message : 'Analysis failed.');
    } finally {
      setBusyAction(null);
    }
  }

  async function handleEvaluateClaudeResults() {
    if (!backendResult || visibleResults.length === 0) return;

    try {
      setIsClaudeEvaluating(true);
      setClaudeError('');
      setClaudeResult(
        await evaluateClaudeAbnormalResults(
          backendResult.analysis_run_id,
          Math.min(visibleResults.length, 5),
          clinicalIntake,
        ),
      );
    } catch (error) {
      setClaudeError(
        error instanceof Error ? error.message : 'Yapay zekâ değerlendirmesi başarısız oldu.',
      );
    } finally {
      setIsClaudeEvaluating(false);
    }
  }

  return (
    <div className="space-y-8">
      <header>
        <p className="text-sm font-semibold uppercase text-cyan-700">
          Yapay Zekâ Laboratuvar Analizi
        </p>
        <h2 className="mt-2 text-3xl font-semibold text-slate-950">
          Klinik değerlendirme ve laboratuvar çalışma alanı
        </h2>
        <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-500">
          Hasta bilgilerini, başvuru nedenini, klinik öyküyü, fizik muayeneyi,
          laboratuvar sonuçlarını ve görüntüleme raporlarını tek analiz kaydında
          topla.
        </p>
        <p className="mt-3 inline-flex rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-800">
          Yapay zekâ çıktıları kesin tanı veya otomatik tetkik istemi değildir; hekim
          değerlendirmesi gerekir.
        </p>
      </header>

      <SectionCard
        title="Klinik kayıt"
        description="Alanlar isteğe bağlıdır. Girilen bilgiler analiz kaydına ve yapay zekâ değerlendirme bağlamına eklenir."
      >
        <ClinicalIntakeForm
          value={clinicalIntake}
          onChange={setClinicalIntake}
        />
      </SectionCard>

      <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
        <div className="grid gap-5 xl:grid-cols-2">
          <div className="rounded-xl border border-emerald-200 bg-white p-5">
            <p className="text-sm font-semibold uppercase text-emerald-700">
              PDF Yükleme
            </p>
            <h3 className="mt-1 text-xl font-semibold text-slate-950">
              Laboratuvar PDF&apos;si yükle ve analiz et
            </h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Metin tabanlı PDF&apos;deki desteklenen değerler otomatik çıkarılır,
              referanslarla karşılaştırılır ve anormal sonuçlar işaretlenir.
            </p>
            <div className="mt-4 rounded-lg border border-dashed border-emerald-300 bg-emerald-50/40 p-4">
              <input
                type="file"
                accept="application/pdf,.pdf"
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  setSelectedFile(event.target.files?.[0] ?? null)
                }
                className="block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-slate-950 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-slate-800"
              />
              {selectedFile && (
                <p className="mt-3 text-sm text-slate-600">
                  Seçilen dosya:{' '}
                  <strong className="text-slate-950">{selectedFile.name}</strong>
                </p>
              )}
              <button
                type="button"
                onClick={() => runAction('pdf')}
                disabled={busyAction !== null || !selectedFile}
                className="mt-4 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === 'pdf'
                  ? 'PDF yükleniyor ve analiz ediliyor…'
                  : 'PDF’yi Yükle ve Analiz Et'}
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-cyan-200 bg-white p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-sm font-semibold uppercase text-cyan-700">
                  Manuel Giriş
                </p>
                <h3 className="mt-1 text-xl font-semibold text-slate-950">
                  Laboratuvar sonuçlarını manuel gir
                </h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Manuel değerler aynı alias, referans, kural, trend ve kalıcılık
                  pipeline&apos;ını kullanır.
                </p>
              </div>
              <label className="text-sm font-medium text-slate-700">
                Rapor tarihi
                <input
                  type="date"
                  value={manualReportDate}
                  onChange={(event: ChangeEvent<HTMLInputElement>) =>
                    setManualReportDate(event.target.value)
                  }
                  className="mt-1 block rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-950"
                />
              </label>
            </div>

            <div className="mt-4 max-h-[38rem] space-y-4 overflow-y-auto pr-1">
              {manualRows.map((row, index) => (
                <div
                  key={row.id}
                  className="rounded-lg border border-slate-200 bg-slate-50 p-4"
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold text-slate-950">
                      Sonuç {index + 1}
                    </p>
                    <button
                      type="button"
                      onClick={() => removeManualRow(row.id)}
                      className="text-sm font-semibold text-red-600 hover:text-red-700"
                    >
                      Kaldır
                    </button>
                  </div>

                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    {MANUAL_FIELDS.map((field) => (
                      <label
                        key={field.key}
                        className={`text-sm font-medium text-slate-700 ${
                          field.wide ? 'sm:col-span-2' : ''
                        }`}
                      >
                        {field.label}
                        <input
                          type={field.type ?? 'text'}
                          inputMode={field.inputMode}
                          value={row[field.key]}
                          placeholder={field.placeholder}
                          onChange={(event: ChangeEvent<HTMLInputElement>) =>
                            updateManualRow(
                              row.id,
                              field.key,
                              event.target.value,
                            )
                          }
                          className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950"
                        />
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() =>
                  setManualRows((rows) => [...rows, createManualRow()])
                }
                className="rounded-lg border border-cyan-300 bg-white px-4 py-2 text-sm font-semibold text-cyan-800 hover:bg-cyan-50"
              >
                + Sonuç ekle
              </button>
              <button
                type="button"
                onClick={() => runAction('manual')}
                disabled={busyAction !== null}
                className="rounded-lg bg-cyan-700 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === 'manual'
                  ? 'Kaydediliyor ve analiz ediliyor…'
                  : 'Sonuçları Kaydet ve Analiz Et'}
              </button>
            </div>
          </div>
        </div>

        <div className="mt-5 flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-5 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase text-slate-500">
              Kontrollü Örnek Analiz
            </p>
            <p className="mt-1 font-semibold text-slate-950">
              Örnek hemoglobin sonucunu analiz et
            </p>
          </div>
          <button
            type="button"
            onClick={() => runAction('sample')}
            disabled={busyAction !== null}
            className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {busyAction === 'sample' ? 'Analiz ediliyor…' : 'Örnek Analizi Başlat'}
          </button>
        </div>

        {backendError && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {backendError}
          </div>
        )}

        {backendResult && (
          <div className="mt-4 flex flex-col gap-3 rounded-lg border border-emerald-200 bg-white p-4 text-sm md:flex-row md:items-center md:justify-between">
            <p className="text-slate-600">
              <strong className="text-slate-950">Analiz tamamlandı.</strong>{' '}
              {visibleResults.length} non-normal result(s) are visible; normal
              rows are hidden.
            </p>
            <button
              type="button"
              onClick={() => navigate('/analysis/results')}
              className="rounded-lg bg-blue-700 px-4 py-2 font-semibold text-white hover:bg-blue-800"
            >
              Tüm Sonuçları Gör
            </button>
          </div>
        )}
      </section>

      <SectionCard
        title="Laboratuvar Özeti"
        description="Normal sonuçlar, klinik incelemeyi sadeleştirmek amacıyla gizlenmiştir."
      >
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {summaryCards.map(([title, value, helper]) => (
            <div
              key={title}
              className="rounded-lg border border-slate-200 bg-slate-50 p-4"
            >
              <p className="text-sm font-medium text-slate-600">{title}</p>
              <p className="mt-3 text-3xl font-semibold text-slate-950">
                {value}
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-500">{helper}</p>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Anormal ve Kontrol Gereken Sonuçlar"
        description="Yüksek, düşük ve hekim kontrolü gerektiren sonuçlar ayrı gruplarda gösterilir. Normal sonuçlar bu görünümde gizlidir."
      >
        {!backendResult ? (
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
            Sonuçları görmek için önce bir analiz oluşturun.
          </div>
        ) : visibleResults.length === 0 ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-6 text-sm text-emerald-800">
            No abnormal or review-required result was found. Normal rows remain
            hidden by design.
          </div>
        ) : (
          <div className="space-y-5">
            <ResultGroup
              title="Yüksek Sonuçlar"
              description="Referans aralığının üzerinde."
              results={groupedResults.high}
              tone="high"
            />
            <ResultGroup
              title="Düşük Sonuçlar"
              description="Referans aralığının altında."
              results={groupedResults.low}
              tone="low"
            />
            <ResultGroup
              title="Hekim Kontrolü Gerekenler"
              description="Parametre eşleştirmesi, referans aralığı veya sınıflandırma belirsiz."
              results={groupedResults.review}
              tone="review"
            />
          </div>
        )}
      </SectionCard>

      <section className="rounded-xl border border-violet-200 bg-violet-50 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase text-violet-700">
              Yapay Zekâ Destekli Klinik Değerlendirme
            </p>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">
              Anormal Sonuçları Değerlendir
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              Claude evaluates non-normal structured results together with
              patient information, complaint, history, examination and entered
              imaging reports. The output includes possible conditions and
              laboratory or imaging tests a physician may consider.
            </p>
          </div>
          <button
            type="button"
            onClick={handleEvaluateClaudeResults}
            disabled={
              !backendResult ||
              visibleResults.length === 0 ||
              isClaudeEvaluating
            }
            className="rounded-lg bg-violet-700 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isClaudeEvaluating
              ? 'Yapay zekâ değerlendiriyor…'
              : 'Tüm Verilerle Değerlendir'}
          </button>
        </div>

        {!backendResult && (
          <p className="mt-4 text-sm text-slate-600">
            Yapay zekâ değerlendirmesi için önce laboratuvar analizi oluşturun.
          </p>
        )}
        {backendResult && visibleResults.length === 0 && (
          <p className="mt-4 text-sm text-slate-600">
            Claude evaluation is disabled because there are no non-normal
            results.
          </p>
        )}
        {claudeError && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {claudeError}
          </div>
        )}

        {claudeResult && (
          <div className="mt-5 space-y-4">
            <div className="rounded-lg border border-violet-200 bg-white p-4 text-sm text-slate-700">
              Yapay zekâ {claudeResult.created_count} physician-review
              evaluation(s).
            </div>

            {claudeResult.created_hypotheses.map((hypothesis) => (
              <ClaudeEvaluationCard
                key={hypothesis.id}
                hypothesis={hypothesis}
              />
            ))}

            {claudeResult.created_hypotheses.length === 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                Claude did not return an evaluation that passed the safety and
                evidence checks.
              </div>
            )}

            {claudeResult.warnings.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                <p className="text-sm font-semibold text-amber-900">Warnings</p>
                <ul className="mt-2 space-y-1 text-sm text-amber-800">
                  {claudeResult.warnings.map((warning) => (
                    <li key={warning}>• {warning}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      <SectionCard
        title="Continue the workflow"
        description="Open the persisted analysis and physician-review queues."
      >
        <div className="grid gap-4 md:grid-cols-3">
          {[
            [
              'View Analysis Results',
              'Open the complete stored analysis record.',
              '/analysis/results',
              !backendResult,
            ],
            [
              'Open Clinical Review Prompts',
              'Review Claude and structured physician prompts.',
              '/clinical-hypotheses',
              !backendResult,
            ],
            [
              'Open Timeline',
              'See analysis and review events over time.',
              '/timeline',
              false,
            ],
          ].map(([label, description, to, disabled]) =>
            disabled ? (
              <div
                key={String(label)}
                className="cursor-not-allowed rounded-lg border border-slate-200 bg-slate-50 p-4 opacity-60"
              >
                <p className="font-semibold text-slate-950">{label}</p>
                <p className="mt-2 text-sm text-slate-500">{description}</p>
              </div>
            ) : (
              <Link
                key={String(label)}
                to={String(to)}
                className="rounded-lg border border-slate-200 bg-white p-4 hover:border-blue-200 hover:bg-blue-50"
              >
                <p className="font-semibold text-slate-950">{label}</p>
                <p className="mt-2 text-sm text-slate-500">{description}</p>
              </Link>
            ),
          )}
        </div>
      </SectionCard>
    </div>
  );
}
