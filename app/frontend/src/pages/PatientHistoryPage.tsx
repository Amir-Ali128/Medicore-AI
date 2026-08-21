import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import SectionCard from '../components/ui/SectionCard';
import {
  activatePatientRecord,
  listPatientRecords,
  type PatientRecord,
} from '../services/patientClient';

function formatDate(value: string) {
  return new Intl.DateTimeFormat('tr-TR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
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
  onRestore,
}: {
  record: PatientRecord;
  onRestore: (record: PatientRecord) => void;
}) {
  const age = record.metadata_json?.age;
  const summary = recordSummary(record);

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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    async function loadRecords() {
      try {
        setLoading(true);
        setError('');
        const response = await listPatientRecords();
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
          Hasta Bilgileri ekranında Kaydet'e bastığınız bilgiler hesabınızda saklanır ve sonraki girişlerinizde yeniden açılabilir.
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
              onRestore={handleRestore}
            />
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
