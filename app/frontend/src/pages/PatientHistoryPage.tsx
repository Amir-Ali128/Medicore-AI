import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import SectionCard from '../components/ui/SectionCard';
import type { LabReportSummary } from '../services/labAnalysisClient';
import {
  listPatientLabReports,
  openLabReportPdf,
} from '../services/labArchiveClient';
import {
  activatePatientRecord,
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

function clip(value: string | null | undefined, max = 150) {
  const text = value?.trim();
  if (!text) return null;
  return text.length > max ? `${text.slice(0, max).trim()}…` : text;
}

function recordSummary(record: PatientRecord) {
  const context = record.metadata_json?.clinical_context;
  if (!context) return [];

  return [
    ['Şikâyet', clip(context.presenting_complaint.chief_complaint)],
    ['Mevcut hastalıklar', clip(context.clinical_history_details.current_medical_conditions)],
    ['Geçmiş sağlık öyküsü', clip(context.clinical_history_details.past_medical_history)],
    ['Kullanılan ilaçlar', clip(context.clinical_history_details.medications)],
  ].filter((item): item is [string, string] => Boolean(item[1]));
}

function RecordCard({
  record,
  attachments,
  onRestore,
}: {
  record: PatientRecord;
  attachments?: AttachmentSummary;
  onRestore: (record: PatientRecord) => void;
}) {
  const [labOpen, setLabOpen] = useState(false);
  const [openingLabId, setOpeningLabId] = useState<string | null>(null);
  const [labOpenError, setLabOpenError] = useState('');
  const age = record.metadata_json?.age;
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
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-lg font-semibold text-slate-950">Hasta kaydı</p>
          <p className="mt-1 text-sm text-slate-500">
            {age !== null && age !== undefined ? `${age} yaş` : 'Yaş bilgisi yok'} ·{' '}
            {sexLabel(record.sex)}
          </p>
          <p className="mt-2 text-xs text-slate-400">
            Son güncelleme: {formatDate(record.updated_at)}
          </p>
        </div>

        <button
          type="button"
          onClick={() => onRestore(record)}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          Kaydı aç
        </button>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <button
          type="button"
          onClick={() => {
            setLabOpen((current) => !current);
            setLabOpenError('');
          }}
          className="rounded-lg border border-emerald-200 bg-emerald-50/60 p-4 text-left transition hover:bg-emerald-50"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">
                Laboratuvar
              </p>
              <p className="mt-2 text-sm font-semibold text-slate-900">
                {attachments ? `${attachments.labCount} kayıt` : 'Kontrol ediliyor…'}
              </p>
              {attachments?.latestLabFile ? (
                <p className="mt-1 truncate text-xs text-slate-500">Son: {attachments.latestLabFile}</p>
              ) : null}
            </div>
            <span className="shrink-0 text-xs font-semibold text-emerald-700">
              {labOpen ? 'PDF’leri gizle' : 'PDF’leri aç'}
            </span>
          </div>
        </button>

        <div className="rounded-lg border border-violet-200 bg-violet-50/60 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-violet-800">
            Radyoloji / diğer tetkikler
          </p>
          <p className="mt-2 text-sm font-semibold text-slate-900">
            {attachments ? `${attachments.radiologyCount} kayıt` : 'Kontrol ediliyor…'}
          </p>
          {attachments?.latestRadiologyFile ? (
            <p className="mt-1 truncate text-xs text-slate-500">Son: {attachments.latestRadiologyFile}</p>
          ) : null}
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
                        {!canOpen ? ' · Eski kayıt, özgün PDF saklanmamış' : ''}
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

      {summary.length > 0 ? (
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {summary.map(([label, value]) => (
            <div key={label} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
              <p className="mt-2 text-sm leading-6 text-slate-800">{value}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-5 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
          Bu kayıtta henüz klinik öykü bilgisi bulunmuyor.
        </p>
      )}
    </article>
  );
}

export default function PatientHistoryPage() {
  const navigate = useNavigate();
  const [records, setRecords] = useState<PatientRecord[]>([]);
  const [attachments, setAttachments] = useState<Record<string, AttachmentSummary>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    async function loadRecords() {
      try {
        setLoading(true);
        setError('');
        const response = await listPatientRecords();
        if (cancelled) return;
        setRecords(response);

        const summaries = await Promise.all(
          response.map(async (record) => {
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

        if (!cancelled) setAttachments(Object.fromEntries(summaries));
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

  function handleRestore(record: PatientRecord) {
    activatePatientRecord(record);
    navigate('/patients/demo');
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">
          Hasta Arşivi
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">Kaydedilen bilgiler</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          Klinik bilgiler, laboratuvar sonuçları ve özgün PDF&apos;ler ile radyoloji ve diğer tetkik dosyaları aynı hasta kaydı altında tutulur.
        </p>
      </header>

      <SectionCard
        title="Hasta kayıtları"
        description={loading ? 'Kayıtlar yükleniyor…' : `${records.length} kayıt bulunuyor.`}
      >
        {error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            {error}
          </div>
        ) : null}

        {!loading && !error && records.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
            <p className="font-semibold text-slate-900">Henüz kaydedilmiş bilgi yok</p>
            <p className="mt-2 text-sm text-slate-500">
              Hasta Bilgileri bölümündeki Kaydet düğmesine bastığınızda kayıt burada görünecek.
            </p>
          </div>
        ) : null}

        <div className="space-y-4">
          {records.map((record) => (
            <RecordCard
              key={record.id}
              record={record}
              attachments={attachments[record.id]}
              onRestore={handleRestore}
            />
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
