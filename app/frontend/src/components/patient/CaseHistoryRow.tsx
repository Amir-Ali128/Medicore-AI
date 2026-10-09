import { useEffect, useRef, useState } from 'react';
import { caseDisplayName } from '../../services/caseManagement';
import { renamePatientCase, type PatientRecord } from '../../services/patientClient';

type Props = {
  record: PatientRecord; active: boolean; deleting: boolean; expanded: boolean;
  onOpen: (record: PatientRecord) => void; onDelete: (record: PatientRecord) => void;
  onToggleDetails: () => void; onRenamed: (record: PatientRecord) => void;
};

export default function CaseHistoryRow({ record, active, deleting, expanded, onOpen, onDelete, onToggleDetails, onRenamed }: Props) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);

  async function saveName(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim() || pending.current) return;
    const controller = new AbortController();
    pending.current = controller; setBusy(true); setError('');
    try {
      const renamed = await renamePatientCase(record.id, name, controller.signal);
      if (controller.signal.aborted) return;
      onRenamed(renamed); setEditing(false);
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Vaka adı değiştirilemedi. Lütfen tekrar deneyin.');
    } finally {
      pending.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <article className={`rounded-2xl border bg-white p-4 shadow-sm ${active ? 'border-blue-300 ring-2 ring-blue-50' : 'border-slate-200'}`}>
    <div className="flex items-center justify-between gap-3">
      <div className="min-w-0">
        <button type="button" onClick={() => onOpen(record)} className="break-words text-left text-base font-semibold text-slate-950 hover:text-blue-700">
          {caseDisplayName(record)}
        </button>
        {active ? <span className="ml-2 rounded-full bg-blue-100 px-2 py-1 text-xs font-semibold text-blue-700">Aktif vaka</span> : null}
        <p className="mt-1 text-xs text-slate-500">Protokol: {record.protocol_no} · Son güncelleme: {new Date(record.updated_at).toLocaleDateString('tr-TR')}</p>
      </div>
      <div className="flex shrink-0 items-start gap-2">
        <button type="button" onClick={() => onOpen(record)} className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">Aç</button>
        <details className="relative">
          <summary aria-label={`${caseDisplayName(record)} işlemleri`} className="cursor-pointer list-none rounded-xl border border-slate-200 px-3 py-2 text-sm font-bold text-slate-700">⋯</summary>
          <div className="absolute right-0 z-10 mt-2 w-44 rounded-xl border border-slate-200 bg-white p-1 shadow-lg">
            <button type="button" onClick={(event) => { event.currentTarget.closest('details')?.removeAttribute('open'); onOpen(record); }} className="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50">Aç</button>
            <button type="button" disabled={busy} onClick={(event) => { event.currentTarget.closest('details')?.removeAttribute('open'); setName(caseDisplayName(record)); setError(''); setEditing(true); }} className="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50">Adını Değiştir</button>
            <button type="button" onClick={(event) => { event.currentTarget.closest('details')?.removeAttribute('open'); onToggleDetails(); }} className="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50">{expanded ? 'Detayları gizle' : 'Detayları göster'}</button>
            <button type="button" disabled={deleting || busy} onClick={() => onDelete(record)} className="block w-full rounded-lg px-3 py-2 text-left text-sm text-red-700 hover:bg-red-50 disabled:opacity-40">{deleting ? 'Siliniyor…' : 'Sil'}</button>
          </div>
        </details>
      </div>
    </div>
    {editing ? <form onSubmit={saveName} className="mt-4 border-t border-slate-100 pt-4">
      <label className="block text-sm font-medium text-slate-700">Vaka adı
        <input autoFocus type="text" maxLength={80} value={name} disabled={busy} onChange={(event) => setName(event.target.value)} className="mt-1 block w-full rounded-xl border border-slate-300 px-3 py-2 text-sm disabled:opacity-50" />
      </label>
      <p className="mt-2 text-xs text-slate-500">Yalnızca görünen ad değişir; vaka kimliği ve kayıtları korunur.</p>
      {error ? <p role="alert" className="mt-2 text-sm text-red-700">{error}</p> : null}
      <div className="mt-3 flex gap-2">
        <button type="submit" disabled={busy || !name.trim()} className="rounded-xl bg-slate-950 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">{busy ? 'Kaydediliyor…' : 'Adı kaydet'}</button>
        <button type="button" disabled={busy} onClick={() => setEditing(false)} className="rounded-xl border border-slate-200 px-4 py-2 text-sm">İptal</button>
      </div>
    </form> : null}
  </article>;
}
