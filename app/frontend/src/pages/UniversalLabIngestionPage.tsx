import { useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

import { getActivePatientId } from '../services/patientClient';
import {
  ingestLabFile,
  ingestLabIntegration,
  ingestManualLabs,
  type LabFileSource,
  type LabIntegrationType,
  type ManualLabRowInput,
  type UniversalLabIngestionResponse,
} from '../services/universalLabIngestionClient';

type SourceId =
  | 'enabiz_pdf'
  | 'file_upload'
  | 'photo'
  | 'screenshot'
  | 'manual'
  | 'email_attachment'
  | 'integration';

type SourceCard = {
  id: SourceId;
  icon: string;
  title: string;
  short: string;
  details: string;
};

type ManualRowDraft = {
  id: number;
  name: string;
  value: string;
  unit: string;
  refMin: string;
  refMax: string;
  refText: string;
  measuredAt: string;
};

type TrustedLabRow = Record<string, unknown>;

const SOURCES: SourceCard[] = [
  {
    id: 'enabiz_pdf',
    icon: '🇹🇷',
    title: 'e-Nabız PDF',
    short: 'e-Nabızdan dışa aktarılan PDF',
    details: 'PDF doğrudan belge okuma katmanına gider, ardından C++ trust motorundan geçer.',
  },
  {
    id: 'file_upload',
    icon: '📁',
    title: 'Dosya Yükleme',
    short: 'PDF, görsel, JSON, CSV veya HL7/TXT',
    details: 'Genel dosya girişi; desteklenen formata göre güvenli adapter otomatik seçilir.',
  },
  {
    id: 'photo',
    icon: '📷',
    title: 'Fotoğraf',
    short: 'Laboratuvar raporu fotoğrafı',
    details: 'PNG, JPEG veya WebP rapor fotoğrafı belge okuma katmanında işlenir.',
  },
  {
    id: 'screenshot',
    icon: '📱',
    title: 'Ekran Görüntüsü',
    short: 'Portal veya uygulama ekran görüntüsü',
    details: 'PNG, JPEG veya WebP ekran görüntüsü ayrı provenance kaynağı olarak tutulur.',
  },
  {
    id: 'manual',
    icon: '⌨️',
    title: 'Manuel Giriş',
    short: 'Test adı, değer, birim ve referans',
    details: 'Sayısal değerler elle girilir; değerler sessizce düzeltilmeden C++ trust katmanına gönderilir.',
  },
  {
    id: 'email_attachment',
    icon: '📎',
    title: 'E-posta Eki',
    short: 'Yetkilendirilmiş eki yükle',
    details: 'Mailbox erişimi yapılmaz; yalnız senin seçtiğin e-posta eki işlenir.',
  },
  {
    id: 'integration',
    icon: '🔌',
    title: 'HL7 / FHIR / API',
    short: 'Yapılandırılmış entegrasyon verisi',
    details: 'HL7 ORU metni, FHIR JSON veya REST JSON doğrudan canonical modele alınır.',
  },
];

const FILE_ENDPOINTS: Partial<Record<SourceId, LabFileSource>> = {
  enabiz_pdf: 'enabiz-pdf',
  file_upload: 'file',
  photo: 'photo',
  screenshot: 'screenshot',
  email_attachment: 'email-attachment',
};

const ACCEPTS: Partial<Record<SourceId, string>> = {
  enabiz_pdf: 'application/pdf,.pdf',
  file_upload:
    'application/pdf,.pdf,image/png,.png,image/jpeg,.jpg,.jpeg,image/webp,.webp,application/json,.json,text/csv,.csv,text/plain,.hl7,.txt',
  photo: 'image/png,.png,image/jpeg,.jpg,.jpeg,image/webp,.webp',
  screenshot: 'image/png,.png,image/jpeg,.jpg,.jpeg,image/webp,.webp',
  email_attachment:
    'application/pdf,.pdf,image/png,.png,image/jpeg,.jpg,.jpeg,image/webp,.webp,application/json,.json,text/csv,.csv,text/plain,.hl7,.txt',
};

function blankManualRow(id: number): ManualRowDraft {
  return {
    id,
    name: '',
    value: '',
    unit: '',
    refMin: '',
    refMax: '',
    refText: '',
    measuredAt: '',
  };
}

function optionalNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value.replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : null;
}

function displayScalar(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text ? text : null;
}

function normalizeLabName(value: unknown) {
  return (displayScalar(value) ?? '').toLocaleLowerCase('tr-TR');
}

function findTrustedRowForTrend(
  trendTest: string | null | undefined,
  trustedRows: TrustedLabRow[],
): TrustedLabRow | undefined {
  const target = normalizeLabName(trendTest);
  if (!target) return undefined;

  return trustedRows.find((row) =>
    [row.display_name, row.canonical_name, row.raw_parameter_name].some(
      (candidate) => normalizeLabName(candidate) === target,
    ),
  );
}

function resultStatus(row?: TrustedLabRow) {
  return (displayScalar(row?.result_status) ?? '').toUpperCase();
}

function isAbnormalTrustedRow(row?: TrustedLabRow) {
  const status = resultStatus(row);
  return status === 'LOW' || status === 'HIGH';
}

function abnormalResultStatus(row?: TrustedLabRow) {
  const status = resultStatus(row);
  if (status === 'LOW') {
    return {
      label: '↓ Düşük',
      className: 'border-blue-200 bg-blue-50 text-blue-800',
    };
  }
  if (status === 'HIGH') {
    return {
      label: '↑ Yüksek',
      className: 'border-red-200 bg-red-50 text-red-800',
    };
  }
  return null;
}

function formatLabValue(value: unknown, unit: string | null) {
  const displayed = displayScalar(value) ?? '—';
  return unit ? `${displayed} ${unit}` : displayed;
}

function formatReferenceRange(row: TrustedLabRow | undefined, unit: string | null) {
  if (!row) return null;

  const referenceText = displayScalar(row.reference_text);
  if (referenceText) return referenceText;

  const minimum = displayScalar(row.reference_min ?? row.extracted_reference_min);
  const maximum = displayScalar(row.reference_max ?? row.extracted_reference_max);
  let range: string | null = null;

  if (minimum !== null && maximum !== null) range = `${minimum} – ${maximum}`;
  else if (minimum !== null) range = `≥ ${minimum}`;
  else if (maximum !== null) range = `≤ ${maximum}`;

  return range && unit ? `${range} ${unit}` : range;
}

function formatTrendStatus(status?: string) {
  const normalized = (status || '').toUpperCase();
  if (normalized === 'UP') return '↑ Yükseliyor';
  if (normalized === 'DOWN') return '↓ Düşüyor';
  if (normalized === 'STABLE') return '→ Stabil';
  if (normalized === 'NO_PREVIOUS_RESULT') return 'İlk ölçüm';
  return status || 'Bilinmiyor';
}

function sourceLabel(sourceType?: string) {
  return SOURCES.find((item) => item.id === sourceType)?.title ?? sourceType ?? 'Laboratuvar girişi';
}

function buildTechnicalResult(result: UniversalLabIngestionResponse) {
  const trustedRows = result.trusted_rows ?? [];
  const abnormalRows = trustedRows.filter((row) => isAbnormalTrustedRow(row));
  const abnormalTrends = (result.longitudinal_trends ?? []).filter((trend) => {
    const trustedRow = findTrustedRowForTrend(trend.test, trustedRows);
    return isAbnormalTrustedRow(trustedRow);
  });

  const {
    trusted_rows: _trustedRows,
    review_rows: _reviewRows,
    longitudinal_trends: _longitudinalTrends,
    clinical_assessment: _clinicalAssessment,
    ...technicalMetadata
  } = result;

  return {
    ...technicalMetadata,
    technical_view: 'abnormal_and_review_only',
    abnormal_trusted_count: abnormalRows.length,
    normal_rows_omitted: Math.max(0, trustedRows.length - abnormalRows.length),
    abnormal_rows: abnormalRows,
    review_rows: result.review_rows ?? [],
    abnormal_longitudinal_trends: abnormalTrends,
  };
}

export default function UniversalLabIngestionPage() {
  const patientId = getActivePatientId();
  const [selectedSource, setSelectedSource] = useState<SourceId>('enabiz_pdf');
  const [file, setFile] = useState<File | null>(null);
  const [clinicalAi, setClinicalAi] = useState(true);
  const [sourceRecordId, setSourceRecordId] = useState('');
  const [reportDate, setReportDate] = useState('');
  const [patientAge, setPatientAge] = useState('');
  const [patientSex, setPatientSex] = useState('');
  const [manualRows, setManualRows] = useState<ManualRowDraft[]>([blankManualRow(1)]);
  const [nextManualId, setNextManualId] = useState(2);
  const [integrationType, setIntegrationType] = useState<LabIntegrationType>('hl7_oru');
  const [integrationPayload, setIntegrationPayload] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<UniversalLabIngestionResponse | null>(null);

  const selected = useMemo(
    () => SOURCES.find((item) => item.id === selectedSource) ?? SOURCES[0],
    [selectedSource],
  );

  function chooseSource(source: SourceId) {
    setSelectedSource(source);
    setFile(null);
    setError('');
    setResult(null);
  }

  function updateManualRow(id: number, patch: Partial<ManualRowDraft>) {
    setManualRows((rows) => rows.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  }

  function addManualRow() {
    setManualRows((rows) => [...rows, blankManualRow(nextManualId)]);
    setNextManualId((value) => value + 1);
  }

  function removeManualRow(id: number) {
    setManualRows((rows) => (rows.length === 1 ? rows : rows.filter((row) => row.id !== id)));
  }

  function buildManualPayload(): ManualLabRowInput[] {
    return manualRows.map((row, index) => {
      const name = row.name.trim();
      const value = optionalNumber(row.value);
      if (!name) throw new Error(`${index + 1}. satırda test adı gerekli.`);
      if (value === null) throw new Error(`${name} için geçerli sayısal değer gir.`);
      return {
        raw_parameter_name: name,
        raw_value: row.value.trim(),
        normalized_value: value,
        unit: row.unit.trim() || null,
        reference_min: optionalNumber(row.refMin),
        reference_max: optionalNumber(row.refMax),
        reference_text: row.refText.trim() || null,
        measured_at: row.measuredAt || null,
      };
    });
  }

  function parsedIntegrationPayload(): unknown {
    if (!integrationPayload.trim()) throw new Error('Entegrasyon payload’u boş olamaz.');
    if (integrationType === 'hl7_oru') return integrationPayload;
    try {
      return JSON.parse(integrationPayload);
    } catch {
      throw new Error('FHIR / REST payload geçerli JSON olmalıdır.');
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setResult(null);

    try {
      const options = {
        patientId,
        clinicalAi,
        sourceRecordId: sourceRecordId.trim() || null,
      };

      let response: UniversalLabIngestionResponse;
      if (selectedSource === 'manual') {
        const age = optionalNumber(patientAge);
        response = await ingestManualLabs(
          {
            labs: buildManualPayload(),
            patient_age: age,
            patient_sex: patientSex.trim() || null,
            report_date: reportDate || null,
            source_record_id: sourceRecordId.trim() || null,
          },
          options,
        );
      } else if (selectedSource === 'integration') {
        response = await ingestLabIntegration(
          integrationType,
          parsedIntegrationPayload(),
          options,
        );
      } else {
        const endpoint = FILE_ENDPOINTS[selectedSource];
        if (!endpoint) throw new Error('Bu kaynak için dosya endpoint’i bulunamadı.');
        if (!file) throw new Error('Önce bir dosya seçmelisin.');
        response = await ingestLabFile(endpoint, file, options);
      }
      setResult(response);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'Laboratuvar verisi işlenemedi.',
      );
    } finally {
      setBusy(false);
    }
  }

  const trustedCount = result?.trusted_count ?? result?.patient_history?.trusted_count ?? 0;
  const reviewCount = result?.review_count ?? result?.patient_history?.review_count ?? 0;
  const processedCount = result?.processed_row_count ?? trustedCount + reviewCount;
  const trends = result?.longitudinal_trends ?? [];
  const trustedRows = result?.trusted_rows ?? [];
  const abnormalRows = trustedRows.filter((row) => isAbnormalTrustedRow(row));
  const abnormalTrends = trends.filter((trend) => {
    const trustedRow = findTrustedRowForTrend(trend.test, trustedRows);
    return isAbnormalTrustedRow(trustedRow);
  });
  const hiddenNormalCount = Math.max(0, trends.length - abnormalTrends.length);
  const technicalResult = result ? buildTechnicalResult(result) : null;
  const isSaved = Boolean(result?.patient_history);

  return (
    <div className="space-y-7">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">
            Universal Lab Ingestion
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950">
            Laboratuvar Verisi Ekle
          </h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
            Yedi kaynaktan gelen laboratuvar verisi aynı canonical modele, C++ trust motoruna,
            hasta geçmişine ve isteğe bağlı klinik AI katmanına bağlanır.
          </p>
        </div>
        <Link
          to="/analysis/mock"
          className="inline-flex w-fit rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          Eski analiz / arşiv görünümü
        </Link>
      </header>

      <div
        className={`rounded-xl border p-4 text-sm ${
          patientId
            ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
            : 'border-amber-200 bg-amber-50 text-amber-900'
        }`}
      >
        {patientId ? (
          <>
            <strong>✓ Aktif hasta bağlı.</strong> Bu giriş hasta geçmişine kaydedilecek ve varsa
            önceki trusted sonuçlarla trend hesaplanacak.
          </>
        ) : (
          <>
            <strong>Aktif hasta seçilmedi.</strong> Veriyi yine işleyebilirsin ancak geçmişe
            kaydetmek ve trend görmek için önce{' '}
            <Link to="/patients/demo" className="font-bold underline">
              Hasta Bilgileri
            </Link>{' '}
            bölümünden hasta kaydı oluştur.
          </>
        )}
      </div>

      <section>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {SOURCES.map((source) => {
            const active = source.id === selectedSource;
            return (
              <button
                key={source.id}
                type="button"
                onClick={() => chooseSource(source.id)}
                className={`rounded-2xl border p-4 text-left transition ${
                  active
                    ? 'border-blue-400 bg-blue-50 ring-2 ring-blue-100'
                    : 'border-slate-200 bg-white hover:border-blue-200 hover:bg-slate-50'
                }`}
              >
                <div className="flex items-start gap-3">
                  <span className="text-2xl" aria-hidden="true">{source.icon}</span>
                  <div>
                    <p className="font-semibold text-slate-950">{source.title}</p>
                    <p className="mt-1 text-xs leading-5 text-slate-500">{source.short}</p>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-start gap-3 border-b border-slate-100 pb-4">
          <span className="text-3xl" aria-hidden="true">{selected.icon}</span>
          <div>
            <h2 className="text-xl font-semibold text-slate-950">{selected.title}</h2>
            <p className="mt-1 text-sm leading-6 text-slate-500">{selected.details}</p>
          </div>
        </div>

        <form onSubmit={submit} className="mt-5 space-y-5">
          {selectedSource === 'manual' ? (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <label className="text-sm font-semibold text-slate-700">
                  Rapor tarihi
                  <input
                    type="date"
                    value={reportDate}
                    onChange={(event) => setReportDate(event.target.value)}
                    className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                </label>
                <label className="text-sm font-semibold text-slate-700">
                  Hasta yaşı
                  <input
                    type="number"
                    min="0"
                    max="130"
                    step="any"
                    value={patientAge}
                    onChange={(event) => setPatientAge(event.target.value)}
                    className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    placeholder="23"
                  />
                </label>
                <label className="text-sm font-semibold text-slate-700">
                  Cinsiyet
                  <input
                    value={patientSex}
                    onChange={(event) => setPatientSex(event.target.value)}
                    className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    placeholder="M / F"
                  />
                </label>
              </div>

              <div className="space-y-3">
                {manualRows.map((row, index) => (
                  <div key={row.id} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <div className="mb-3 flex items-center justify-between">
                      <p className="text-sm font-semibold text-slate-800">Sonuç {index + 1}</p>
                      <button
                        type="button"
                        onClick={() => removeManualRow(row.id)}
                        disabled={manualRows.length === 1}
                        className="text-xs font-semibold text-red-600 disabled:opacity-30"
                      >
                        Kaldır
                      </button>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                      <input
                        value={row.name}
                        onChange={(event) => updateManualRow(row.id, { name: event.target.value })}
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                        placeholder="Test adı · HbA1c"
                      />
                      <input
                        value={row.value}
                        onChange={(event) => updateManualRow(row.id, { value: event.target.value })}
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                        inputMode="decimal"
                        placeholder="Değer · 8.1"
                      />
                      <input
                        value={row.unit}
                        onChange={(event) => updateManualRow(row.id, { unit: event.target.value })}
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                        placeholder="Birim · %"
                      />
                      <input
                        type="date"
                        value={row.measuredAt}
                        onChange={(event) => updateManualRow(row.id, { measuredAt: event.target.value })}
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                        title="Ölçüm tarihi"
                      />
                      <input
                        value={row.refMin}
                        onChange={(event) => updateManualRow(row.id, { refMin: event.target.value })}
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                        inputMode="decimal"
                        placeholder="Referans min"
                      />
                      <input
                        value={row.refMax}
                        onChange={(event) => updateManualRow(row.id, { refMax: event.target.value })}
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                        inputMode="decimal"
                        placeholder="Referans max"
                      />
                      <input
                        value={row.refText}
                        onChange={(event) => updateManualRow(row.id, { refText: event.target.value })}
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm md:col-span-2"
                        placeholder="Referans metni · 4.0–6.5"
                      />
                    </div>
                  </div>
                ))}
              </div>

              <button
                type="button"
                onClick={addManualRow}
                className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-semibold text-blue-700"
              >
                + Sonuç ekle
              </button>
            </div>
          ) : selectedSource === 'integration' ? (
            <div className="space-y-3">
              <label className="block text-sm font-semibold text-slate-700">
                Entegrasyon türü
                <select
                  value={integrationType}
                  onChange={(event) => setIntegrationType(event.target.value as LabIntegrationType)}
                  className="mt-1 block w-full max-w-sm rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                >
                  <option value="hl7_oru">HL7 ORU</option>
                  <option value="fhir">FHIR JSON</option>
                  <option value="rest">REST / API JSON</option>
                </select>
              </label>
              <label className="block text-sm font-semibold text-slate-700">
                Payload
                <textarea
                  rows={12}
                  value={integrationPayload}
                  onChange={(event) => setIntegrationPayload(event.target.value)}
                  className="mt-1 block w-full rounded-xl border border-slate-300 bg-slate-950 p-4 font-mono text-xs leading-6 text-slate-100"
                  placeholder={
                    integrationType === 'hl7_oru'
                      ? 'MSH|^~\\&|...\nPID|...\nOBR|...\nOBX|1|NM|4548-4^HbA1c^LN||8.1|%|4.0-6.5'
                      : '{\n  "resourceType": "Observation"\n}'
                  }
                />
              </label>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-blue-300 bg-blue-50/40 p-5">
              <input
                type="file"
                accept={ACCEPTS[selectedSource]}
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-700 file:px-4 file:py-2.5 file:text-sm file:font-semibold file:text-white hover:file:bg-blue-800"
              />
              {file ? (
                <p className="mt-3 text-sm font-medium text-slate-800">
                  {file.name} · {(file.size / (1024 * 1024)).toFixed(2)} MB
                </p>
              ) : null}
            </div>
          )}

          <div className="grid gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 md:grid-cols-[1fr_auto] md:items-end">
            <label className="block text-sm font-semibold text-slate-700">
              Kaynak kayıt ID (opsiyonel)
              <input
                value={sourceRecordId}
                onChange={(event) => setSourceRecordId(event.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                placeholder="Kurum / rapor / mesaj ID"
              />
            </label>
            <label className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700">
              <input
                type="checkbox"
                checked={clinicalAi}
                onChange={(event) => setClinicalAi(event.target.checked)}
                className="h-4 w-4"
              />
              Klinik AI çalıştır
            </label>
          </div>

          {error ? (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm leading-6 text-red-800">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-blue-700 px-6 py-3 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? 'C++ Trust + AI işleniyor…' : 'İşle ve Sonucu Göster'}
          </button>
        </form>
      </section>

      {result ? (
        <section className="space-y-4 rounded-2xl border border-emerald-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-emerald-700">
                İşlem tamamlandı
              </p>
              <h2 className="mt-1 text-xl font-semibold text-slate-950">
                {sourceLabel(result.source_type)} sonucu
              </h2>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`w-fit rounded-full px-3 py-1 text-xs font-bold ${
                  result.doctor_review_required
                    ? 'bg-amber-100 text-amber-800'
                    : 'bg-emerald-100 text-emerald-800'
                }`}
              >
                {result.doctor_review_required ? 'Hekim kontrolü gerekli' : 'Trust kontrolü tamam'}
              </span>
              <button
                type="button"
                disabled
                title={
                  isSaved
                    ? result.patient_history?.lab_report_id
                      ? `Rapor ID: ${result.patient_history.lab_report_id}`
                      : 'Hasta geçmişine kaydedildi.'
                    : 'Kaydetmek için önce aktif hasta seçmelisin.'
                }
                className={`rounded-lg px-4 py-2 text-sm font-semibold ${
                  isSaved
                    ? 'bg-emerald-700 text-white'
                    : 'cursor-not-allowed border border-slate-300 bg-slate-100 text-slate-400'
                }`}
              >
                {isSaved ? '✓ Kaydedildi' : 'Kaydet'}
              </button>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase text-slate-500">Toplam</p>
              <p className="mt-1 text-2xl font-bold text-slate-950">{processedCount}</p>
            </div>
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
              <p className="text-xs font-semibold uppercase text-emerald-700">Trusted</p>
              <p className="mt-1 text-2xl font-bold text-emerald-900">{trustedCount}</p>
            </div>
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
              <p className="text-xs font-semibold uppercase text-amber-700">Review</p>
              <p className="mt-1 text-2xl font-bold text-amber-900">{reviewCount}</p>
            </div>
            <div className="rounded-xl border border-red-200 bg-red-50 p-4">
              <p className="text-xs font-semibold uppercase text-red-700">Anormal</p>
              <p className="mt-1 text-2xl font-bold text-red-900">{abnormalRows.length}</p>
            </div>
          </div>

          {result.patient_history ? (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-900">
              <strong>✓ Hasta geçmişine kaydedildi.</strong>{' '}
              {result.patient_history.lab_report_id
                ? `Rapor ID: ${result.patient_history.lab_report_id}`
                : ''}
            </div>
          ) : null}

          {result.clinical_assessment?.headline || result.clinical_assessment?.overview ? (
            <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
              <p className="text-xs font-bold uppercase tracking-wide text-blue-700">Klinik AI özeti</p>
              {result.clinical_assessment.headline ? (
                <h3 className="mt-2 font-semibold text-blue-950">{result.clinical_assessment.headline}</h3>
              ) : null}
              {result.clinical_assessment.overview ? (
                <p className="mt-2 text-sm leading-6 text-blue-900">{result.clinical_assessment.overview}</p>
              ) : null}
            </div>
          ) : null}

          {abnormalTrends.length > 0 ? (
            <div>
              <div className="flex flex-wrap items-end justify-between gap-2">
                <h3 className="text-sm font-semibold text-slate-900">Anormal laboratuvar sonuçları ve seyir</h3>
                {hiddenNormalCount > 0 ? (
                  <span className="text-xs font-medium text-slate-500">
                    {hiddenNormalCount} normal sonuç gizlendi
                  </span>
                ) : null}
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {abnormalTrends.map((trend, index) => {
                  const trustedRow = findTrustedRowForTrend(trend.test, trustedRows);
                  const abnormalStatus = abnormalResultStatus(trustedRow);
                  const unit = displayScalar(trustedRow?.unit);
                  const referenceRange = formatReferenceRange(trustedRow, unit);
                  const hasPreviousValue =
                    trend.previous_value !== null && trend.previous_value !== undefined;

                  return (
                    <div
                      key={`${trend.parameter_code ?? trend.test ?? 'trend'}-${index}`}
                      className="rounded-xl border border-slate-200 bg-slate-50 p-4"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-slate-900">
                            {trend.test || trend.parameter_code || 'Laboratuvar sonucu'}
                          </p>
                          <p className="mt-1 text-lg font-bold text-slate-950">
                            {formatLabValue(trend.current_value, unit)}
                          </p>
                        </div>
                        {abnormalStatus ? (
                          <span
                            className={`w-fit rounded-full border px-2.5 py-1 text-xs font-bold ${abnormalStatus.className}`}
                          >
                            {abnormalStatus.label}
                          </span>
                        ) : null}
                      </div>

                      {referenceRange ? (
                        <p className="mt-2 text-xs leading-5 text-slate-500">
                          Referans: {referenceRange}
                        </p>
                      ) : null}

                      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                        <span className="rounded-full bg-white px-2.5 py-1 font-bold text-slate-700 ring-1 ring-slate-200">
                          {formatTrendStatus(trend.trend_status)}
                        </span>
                        {hasPreviousValue ? (
                          <span className="text-slate-500">
                            Önceki: {formatLabValue(trend.previous_value, unit)}
                            {trend.percentage_difference !== null &&
                            trend.percentage_difference !== undefined
                              ? ` · ${trend.percentage_difference > 0 ? '+' : ''}${trend.percentage_difference.toFixed(2)}%`
                              : ''}
                          </span>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
              Trusted sonuçlarda LOW/HIGH sınıfında anormal laboratuvar sonucu yok.
            </div>
          )}

          <details className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <summary className="cursor-pointer text-sm font-semibold text-slate-700">
              Teknik yanıtı göster · yalnız anormal + review
            </summary>
            <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-950 p-4 text-xs leading-5 text-slate-100">
              {JSON.stringify(technicalResult, null, 2)}
            </pre>
          </details>
        </section>
      ) : null}
    </div>
  );
}
