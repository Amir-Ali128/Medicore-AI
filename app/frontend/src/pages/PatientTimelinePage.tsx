import { useEffect, useLayoutEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import PatientTimelinePanel from '../components/patient/PatientTimelinePanel';
import { getActivePatientId, getPatientRecord } from '../services/patientClient';
import { selectPatientScope } from '../services/patientScope';

export default function PatientTimelinePage() {
  const [params] = useSearchParams();
  const patientId = params.get('patient') || getActivePatientId();
  const [header, setHeader] = useState<{ patientId: string; protocolNo: string; error: string } | null>(null);
  useLayoutEffect(() => { if (patientId) selectPatientScope(patientId); }, [patientId]);
  useEffect(() => {
    if (!patientId) return;
    const selectedId = patientId;
    const controller = new AbortController();
    let cancelled = false;
    setHeader(null);
    void getPatientRecord(selectedId, controller.signal).then((record) => {
      if (record.id !== selectedId) throw new Error('Hasta kaydı seçili hastayla eşleşmiyor.');
      if (!cancelled) setHeader({ patientId: selectedId, protocolNo: record.protocol_no, error: '' });
    }).catch((error: unknown) => {
      if (!cancelled) setHeader({ patientId: selectedId, protocolNo: '', error: error instanceof Error ? error.message : 'Hasta kaydı açılamadı.' });
    });
    return () => { cancelled = true; controller.abort(); };
  }, [patientId]);
  if (!patientId) return <div className="rounded-3xl bg-white p-6"><p className="text-slate-600">Geçmişi görmek için bir hasta seç.</p><Link to="/history" className="mt-3 inline-block text-blue-700">Hasta arşivini aç</Link></div>;
  const currentHeader = header?.patientId === patientId ? header : null;
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="rounded-3xl border border-slate-200 bg-white p-6">
        <h1 className="text-2xl font-semibold text-slate-950">Hasta Sağlık Geçmişi</h1>
        {currentHeader?.protocolNo ? <p className="mt-2 font-medium text-blue-700">Protokol / Hasta No: {currentHeader.protocolNo}</p> : null}
        <p className="mt-2 text-sm text-slate-500">Laboratuvar, rapor, klinik bilgi ve vital bulgular tarih sırasıyla gösterilir.</p>
        <Link to={`/case?patient=${encodeURIComponent(patientId)}&step=summary`} className="mt-4 inline-block text-sm font-medium text-blue-700">Vakayı Aç</Link>
      </div>
      <div className="rounded-3xl border border-slate-200 bg-white p-6">
        {currentHeader?.error ? <p role="alert" className="text-sm text-red-700">{currentHeader.error}</p> : currentHeader ? <PatientTimelinePanel key={patientId} patientId={patientId} /> : <p role="status" className="text-sm text-slate-500">Hasta kaydı yükleniyor…</p>}
      </div>
    </div>
  );
}
