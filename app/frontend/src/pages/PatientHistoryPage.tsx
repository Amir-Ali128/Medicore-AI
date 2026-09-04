import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import type { LabReportSummary } from '../services/labAnalysisClient';
import {
  listPatientLabReports,
  openLabReportPdf,
} from '../services/labArchiveClient';
import {
  activatePatientRecord,
  clearActivePatientRecord,
  deletePatientRecord,
  getActivePatientId,
  listPatientRecords,
  type PatientRecord,
} from '../services/patientClient';
import { listPatientRadiologyReports } from '../services/radiologyClient';

type AttachmentSummary = {
  labCount: number;
  radiologyCount: number;
  latestLabFile: string | null;
  latestRadiologyFile: string | null;
  labReports: LabReportSummary[];
};

const PAGE_SIZE = 12;

function formatDate(value: string) {
  return new Intl.DateTimeFormat('tr-TR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

function formatPdfDate(value: string | null | undefined) {
  if (!value) return 'Tarih yok';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium' }).format(parsed);
}

function sexLabel(value: string) {
  switch (value) {
    case 'male': return 'Erkek';
    case 'female': return 'Kadın';
    case 'other': return 'Diğer';
    default: return 'Cinsiyet bilgisi yok';
  }
}

function clip(value: string | null | undefined, max = 110) {
  const text = value?.trim();
  if (!text) return null;
  return text.length > max ? `${text.slice(0, max).trim()}…` : text;
}

function recordDisplayName(record: PatientRecord) {
  const name = record.metadata_json?.clinical_context?.patient_information?.full_name?.trim();
  if (name) return name;
  return `Hasta ${record.protocol_no}`;
}

function recordSearchText(record: PatientRecord) {
  const context = record.metadata_json?.clinical_context;
  const patient = context?.patient_information;
  return [
    record.protocol_no,
    record.external_ref,
    recordDisplayName(record),
    patient?.age,
    sexLabel(record.sex),
    context?.presenting_complaint?.chief_complaint,
    context?.clinical_history_details?.current_medical_conditions,
  ]
    .filter((value) => value !== null && value !== undefined)
    .join(' ')
    .toLocaleLowerCase('tr-TR');
}

function recordSummary(record: PatientRecord) {
  const context = record.metadata_json?.clinical_context;
  if (!context) return [];

  return [
    ['Şikâyet', clip(context.presenting_complaint.chief_complaint)],
    ['Mevcut hastalıklar', clip(context.clinical_history_details.current_medical_conditions)],
  ].filter((item): item is [string, string] => Boolean(item[1]));
}

function RecordCard({
  record,
  attachments,
  active,
  onOpen,
  onDelete,
  deleting,
}: {
  record: PatientRecord;
  attachments?: AttachmentSummary;
  active: boolean;
  onOpen: (record: PatientRecord) => void;
  onDelete: (record: PatientRecord) => void;
  deleting: boolean;
}) {
  const [labOpen, setLabOpen] = useState(false);
  const [openingLabId, setOpeningLabId] = useState<string | null>(null);
  const [labOpenError, setLabOpenError] = useState('');
  const age =
    record.metadata_json?.clinical_context?.patient_information?.age ??
    record.metadata_json?.age ??
    null;
  const summary = recordSummary(record);
  const labPdfs = (attachments?.labReports ?? []).filter((report) =>
    report.file_name?.toLowerCase().endsWith('.pdf'),
  );

  async function handleOpenLabPdf(report: LabReportSummary) {
    setOpeningLabId(report.id);
    setLabOpenError('');
    try {
      await openLabReportPdf(report.id, report.file_name);
    } catch (openError) {
      setLabOpenError(
        openError instanceof Error ? openError.message : 'PDF açılamadı.',
      );
    } finally {
      setOpeningLabId(null);
    }
  }

  return (
    <article className={`rounded-xl border bg-white p-5 shadow-sm ${active ? 'border-blue-300 ring-2 ring-blue-50' : 'border-slate-200'}`}>
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate text-lg font-semibold text-slate-950">
              {recordDisplayName(record)}
            </h2>
            {active ? (
              <span className="rounded-full bg-blue-100 px-2.5 py-1 text-xs font-semibold text-blue-700">
                Aktif hasta
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-sm font-semibold text-cyan-700">
            Protokol / Hasta No: {record.protocol_no}
          </p>
          <p className="mt-1 text-sm text-slate-500">
            {age !== null && age !== undefined ? `${age} yaş` : 'Yaş bilgisi yok'} · {sexLabel(record.sex)}
          </p>
          <p className="mt-2 text-xs text-slate-400">
            Oluşturma: {formatDate(record.created_at)} · Son güncelleme: {formatDate(record.updated_at)}
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onOpen(record)}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
          >
            Kaydı aç
          </button>
          <button
            type="button"
            onClick={() => onOpen(record)}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Düzenle
          </button>
          <button
            type="button"
            onClick={() => onDelete(record)}
            disabled={deleting}
            className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            {deleting ? 'Siliniyor…' : 'Sil'}
          </button>
        </div>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <button
          type="button"
          onClick={() => {
            setLabOpen((current) => !current);
            setLabOpenError('');
          }}
          className="rounded-lg border border-emerald-200 bg-emerald-50/60 p-4 text-left transition hover:bg-emerald-50"
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">Laboratuvar</p>
          <p className="mt-2 text-sm font-semibold text-slate-900">
            {attachments ? `${attachments.labCount} kayıt` : 'Yükleniyor…'}
          </p>
          {attachments?.latestLabFile ? (
            <p className="mt-1 truncate text-xs text-slate-500">Son: {attachments.latestLabFile}</p>
          ) : null}
          <p className="mt-2 text-xs font-semibold text-emerald-700">
            {labOpen ? 'PDF’leri gizle' : 'PDF’leri göster'}
          </p>
        </button>

        <div className="rounded-lg border border-violet-200 bg-violet-50/60 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-violet-800">Radyoloji / diğer tetkikler</p>
          <p className="mt-2 text-sm font-semibold text-slate-900">
            {attachments ? `${attachments.radiologyCount} kayıt` : 'Yükleniyor…'}
          </p>
          {attachments?.latestRadiologyFile ? (
            <p className="mt-1 truncate text-xs text-slate-500">Son: {attachments.latestRadiologyFile}</p>
          ) : null}
        </div>

        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 sm:col-span-2 lg:col-span-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Klinik özet</p>
          {summary.length > 0 ? (
            <div className="mt-2 space-y-1.5">
              {summary.map(([label, value]) => (
                <p key={label} className="text-xs leading-5 text-slate-700">
                  <span className="font-semibold">{label}:</span> {value}
                </p>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-xs leading-5 text-slate-500">Henüz klinik öykü eklenmedi.</p>
          )}
        </div>
      </div>

      {labOpen ? (
        <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50/30 p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-semibold text-slate-900">Laboratuvar PDF&apos;leri</p>
            <span className="text-xs font-semibold text-emerald-700">{labPdfs.length} PDF</span>
          </div>

          {labPdfs.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500">Bu hasta kaydında açılabilir laboratuvar PDF&apos;i yok.</p>
          ) : (
            <div className="mt-3 space-y-2">
              {labPdfs.map((report) => {
                const canOpen = report.metadata_json?.original_file_stored === true;
                return (
                  <div
                    key={report.id}
                    className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-900">
                        📄 {report.file_name || 'Laboratuvar raporu.pdf'}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {formatPdfDate(report.report_date || report.created_at)}
                        {!canOpen ? ' · Özgün PDF saklanmamış' : ''}
                      </p>
                    </div>
                    {canOpen ? (
                      <button
                        type="button"
                        onClick={() => void handleOpenLabPdf(report)}
                        disabled={openingLabId === report.id}
                        className="shrink-0 rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
                      >
                        {openingLabId === report.id ? 'Açılıyor…' : 'PDF’yi aç'}
                      </button>
                    ) : (
                      <span className="shrink-0 text-xs font-semibold text-slate-400">Dosya yok</span>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {labOpenError ? (
            <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {labOpenError}
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

export default function PatientHistoryPage() {
  const navigate = useNavigate();
  const [records, setRecords] = useState<PatientRecord[]>([]);
  const [attachments, setAttachments] = useState<Record<string, AttachmentSummary>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [sexFilter, setSexFilter] = useState('all');
  const [page, setPage] = useState(1);

  useEffect(() => {
    let cancelled = false;

    async function loadRecords() {
      try {
        setLoading(true);
        setError('');
        const response = await listPatientRecords(500);
        if (!cancelled) setRecords(response);
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Hasta kayıtları yüklenemedi.',
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadRecords();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredRecords = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('tr-TR');
    return records.filter((record) => {
      if (sexFilter !== 'all' && record.sex !== sexFilter) return false;
      if (!normalizedQuery) return true;
      return recordSearchText(record).includes(normalizedQuery);
    });
  }, [query, records, sexFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredRecords.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageRecords = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filteredRecords.slice(start, start + PAGE_SIZE);
  }, [currentPage, filteredRecords]);
  const visibleRecordIds = pageRecords.map((record) => record.id).join('|');

  useEffect(() => {
    setPage(1);
  }, [query, sexFilter]);

  useEffect(() => {
    let cancelled = false;
    const recordsNeedingSummary = pageRecords.filter((record) => !attachments[record.id]);
    if (recordsNeedingSummary.length === 0) return;

    async function loadVisibleAttachmentSummaries() {
      const summaries = await Promise.all(
        recordsNeedingSummary.map(async (record) => {
          const [labs, radiology] = await Promise.all([
            listPatientLabReports(record.id).catch(() => []),
            listPatientRadiologyReports(record.id, { includeUnanalyzed: true }).catch(() => []),
          ]);
          return [
            record.id,
            {
              labCount: labs.length,
              radiologyCount: radiology.length,
              latestLabFile: labs[0]?.file_name ?? null,
              latestRadiologyFile: radiology[0]?.file_name ?? null,
              labReports: labs,
            } satisfies AttachmentSummary,
          ] as const;
        }),
      );

      if (!cancelled) {
        setAttachments((current) => ({
          ...current,
          ...Object.fromEntries(summaries),
        }));
      }
    }

    void loadVisibleAttachmentSummaries();
    return () => {
      cancelled = true;
    };
    // visibleRecordIds intentionally represents the current page; existing
    // attachment summaries are cached in state and are not re-requested.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleRecordIds]);

  function handleNewPatient() {
    clearActivePatientRecord();
    navigate('/patients/demo?new=1');
  }

  function handleOpen(record: PatientRecord) {
    activatePatientRecord(record);
    navigate('/patients/demo');
  }

  async function handleDelete(record: PatientRecord) {
    const summary = attachments[record.id];
    const recordCount = (summary?.labCount ?? 0) + (summary?.radiologyCount ?? 0);
    const warning =
      recordCount > 0
        ? `Bu hastaya bağlı ${recordCount} laboratuvar/radyoloji kaydı da birlikte silinecek. `
        : '';
    const confirmed = window.confirm(
      `${warning}Bu hasta kaydı kalıcı olarak silinsin mi? Bu işlem geri alınamaz.`,
    );
    if (!confirmed) return;

    setDeletingId(record.id);
    setError('');
    try {
      await deletePatientRecord(record.id);
      setRecords((current) => current.filter((item) => item.id !== record.id));
      setAttachments((current) => {
        const next = { ...current };
        delete next[record.id];
        return next;
      });
    } catch (deleteError) {
      setError(
        deleteError instanceof Error ? deleteError.message : 'Hasta kaydı silinemedi.',
      );
    } finally {
      setDeletingId(null);
    }
  }

  const knownAttachmentSummaries = Object.values(attachments);
  const knownLabCount = knownAttachmentSummaries.reduce((sum, item) => sum + item.labCount, 0);
  const knownRadiologyCount = knownAttachmentSummaries.reduce((sum, item) => sum + item.radiologyCount, 0);

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">Hasta Arşivi</p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950">Hasta kayıtları</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
            Birden fazla hastayı ayrı kayıtlar halinde yönetin. Her hastanın klinik bilgileri, laboratuvar sonuçları, radyoloji/ultrason raporları ve dosyaları kendi protokolü altında tutulur.
          </p>
        </div>
        <button
          type="button"
          onClick={handleNewPatient}
          className="rounded-lg bg-blue-700 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-blue-800"
        >
          + Yeni Hasta Kaydı
        </button>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Toplam hasta</p>
          <p className="mt-2 text-2xl font-semibold text-slate-950">{records.length}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Filtrelenen</p>
          <p className="mt-2 text-2xl font-semibold text-slate-950">{filteredRecords.length}</p>
        </div>
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Yüklenen lab kayıtları</p>
          <p className="mt-2 text-2xl font-semibold text-slate-950">{knownLabCount}</p>
          <p className="mt-1 text-xs text-slate-500">Görüntülenen hasta sayfaları için</p>
        </div>
        <div className="rounded-xl border border-violet-200 bg-violet-50/50 p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-violet-700">Yüklenen tetkikler</p>
          <p className="mt-2 text-2xl font-semibold text-slate-950">{knownRadiologyCount}</p>
          <p className="mt-1 text-xs text-slate-500">Görüntülenen hasta sayfaları için</p>
        </div>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px_auto]">
          <label className="text-sm font-medium text-slate-700">
            Hasta ara
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Protokol no, hasta bilgisi veya klinik içerik ile ara"
              className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-950 placeholder:text-slate-400"
            />
          </label>
          <label className="text-sm font-medium text-slate-700">
            Cinsiyet
            <select
              value={sexFilter}
              onChange={(event) => setSexFilter(event.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-950"
            >
              <option value="all">Tümü</option>
              <option value="male">Erkek</option>
              <option value="female">Kadın</option>
              <option value="other">Diğer</option>
              <option value="unknown">Bilinmiyor</option>
            </select>
          </label>
          <button
            type="button"
            onClick={() => {
              setQuery('');
              setSexFilter('all');
            }}
            className="self-end rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Filtreleri temizle
          </button>
        </div>
      </section>

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
          Hasta kayıtları yükleniyor…
        </div>
      ) : null}

      {!loading && !error && records.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center">
          <p className="font-semibold text-slate-900">Henüz hasta kaydı yok</p>
          <p className="mt-2 text-sm text-slate-500">
            İlk hastayı oluşturmak için Yeni Hasta Kaydı düğmesini kullanın.
          </p>
          <button
            type="button"
            onClick={handleNewPatient}
            className="mt-5 rounded-lg bg-blue-700 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-800"
          >
            + İlk hastayı oluştur
          </button>
        </div>
      ) : null}

      {!loading && records.length > 0 && filteredRecords.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
          Arama veya filtrelerle eşleşen hasta kaydı bulunamadı.
        </div>
      ) : null}

      <div className="space-y-4">
        {pageRecords.map((record) => (
          <RecordCard
            key={record.id}
            record={record}
            attachments={attachments[record.id]}
            active={getActivePatientId() === record.id}
            onOpen={handleOpen}
            onDelete={(item) => void handleDelete(item)}
            deleting={deletingId === record.id}
          />
        ))}
      </div>

      {filteredRecords.length > 0 ? (
        <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-slate-500">
            {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filteredRecords.length)} / {filteredRecords.length} kayıt
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={currentPage <= 1}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              Önceki
            </button>
            <span className="px-2 text-sm font-semibold text-slate-700">
              {currentPage} / {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              disabled={currentPage >= totalPages}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              Sonraki
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
