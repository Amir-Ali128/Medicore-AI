import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import SectionCard from '../components/ui/SectionCard';
import {
  deletePatientHistoryRecord,
  getPatientHistory,
  restorePatientSession,
  type PatientHistoryRecord,
} from '../services/patientSessionStore';

function formatDate(value: string) {
  return new Intl.DateTimeFormat('tr-TR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

function RecordCard({
  record,
  onRestore,
  onDelete,
}: {
  record: PatientHistoryRecord;
  onRestore: (recordId: string) => void;
  onDelete: (recordId: string) => void;
}) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-lg font-semibold text-slate-950">{record.displayName}</p>
          <p className="mt-1 text-sm text-slate-500">
            {record.age ? `${record.age} yaş` : 'Yaş bilgisi yok'} ·{' '}
            {record.sex ?? 'Cinsiyet bilgisi yok'}
          </p>
          <p className="mt-2 text-xs text-slate-400">
            Kaydedilme tarihi: {formatDate(record.archivedAt)}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onRestore(record.id)}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
          >
            Hastayı aç
          </button>
          <button
            type="button"
            onClick={() => onDelete(record.id)}
            className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50"
          >
            Kaydı kaldır
          </button>
        </div>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-semibold uppercase text-slate-500">Laboratuvar analizi</p>
          <p className="mt-2 text-sm font-medium text-slate-800">
            {record.analysisRunId ? 'Mevcut' : 'Bulunmuyor'}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-semibold uppercase text-slate-500">Laboratuvar raporu</p>
          <p className="mt-2 text-sm font-medium text-slate-800">
            {record.labReportId ? 'Mevcut' : 'Bulunmuyor'}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-semibold uppercase text-slate-500">Radyoloji</p>
          <p className="mt-2 text-sm font-medium text-slate-800">
            {record.radiologyReportId ? 'Mevcut' : 'Bulunmuyor'}
          </p>
        </div>
      </div>
    </article>
  );
}

export default function PatientHistoryPage() {
  const navigate = useNavigate();
  const [version, setVersion] = useState(0);
  const history = useMemo(() => getPatientHistory(), [version]);

  function handleRestore(recordId: string) {
    if (!restorePatientSession(recordId)) return;
    navigate('/patients/demo');
    window.location.reload();
  }

  function handleDelete(recordId: string) {
    const confirmed = window.confirm('Bu hasta kaydı arşivden kaldırılsın mı?');
    if (!confirmed) return;
    deletePatientHistoryRecord(recordId);
    setVersion((current) => current + 1);
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">
          Hasta Arşivi
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">Kaydedilen hastalar</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
          Yeni hastaya geçmeden önce kaydettiğiniz hastaları burada görebilir ve yeniden açabilirsiniz.
        </p>
      </header>

      <SectionCard
        title="Hasta kayıtları"
        description={`${history.length} hasta kaydı bulunuyor.`}
      >
        {history.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
            <p className="font-semibold text-slate-900">Henüz kaydedilmiş hasta yok</p>
            <p className="mt-2 text-sm text-slate-500">
              Üst bardaki “Hastayı kaydet ve temizle” düğmesiyle mevcut hastayı buraya kaydedebilirsiniz.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {history.map((record) => (
              <RecordCard
                key={record.id}
                record={record}
                onRestore={handleRestore}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  );
}
