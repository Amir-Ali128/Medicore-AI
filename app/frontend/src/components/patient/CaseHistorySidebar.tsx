import { useEffect, useId, useRef, useState, useSyncExternalStore } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { caseNameMatches } from '../../services/caseManagement';
import { activatePatientRecord, getActivePatientId, listPatientRecords, type PatientRecord } from '../../services/patientClient';
import { capturePatientScope, patientScopeVersion, subscribePatientScope } from '../../services/patientScope';
import CaseHistoryRow from './CaseHistoryRow';

export default function CaseHistorySidebar({ mobile = false }: { mobile?: boolean }) {
  const location = useLocation();
  const navigate = useNavigate();
  const id = useId();
  const scopeVersion = useSyncExternalStore(subscribePatientScope, patientScopeVersion, patientScopeVersion);
  const owner = capturePatientScope().owner;
  const [open, setOpen] = useState(() => new URLSearchParams(location.search).get('history') === '1');
  const [wide, setWide] = useState(() => typeof window.matchMedia === 'function' ? window.matchMedia('(min-width: 1024px)').matches : true);
  const [records, setRecords] = useState<PatientRecord[]>([]);
  const [recordsOwner, setRecordsOwner] = useState(owner);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  const visible = mobile ? !wide : wide;

  useEffect(() => {
    if (new URLSearchParams(location.search).get('history') === '1') setOpen(true);
  }, [location.key, location.search]);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia('(min-width: 1024px)');
    const update = () => setWide(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    if (!open || !visible) return;
    const reload = () => setRefresh((value) => value + 1);
    window.addEventListener('medicore:case-summary-updated', reload);
    window.addEventListener('medicore:case-name-updated', reload);
    return () => {
      window.removeEventListener('medicore:case-summary-updated', reload);
      window.removeEventListener('medicore:case-name-updated', reload);
    };
  }, [open, visible]);

  useEffect(() => {
    if (!open || !visible) return;
    const controller = new AbortController();
    setLoading(true); setError('');
    // Opening a navigation menu must never auto-save or rewrite a clinical draft.
    void listPatientRecords(500, { syncDraft: false, signal: controller.signal }).then((items) => {
      if (controller.signal.aborted || capturePatientScope().owner !== owner) return;
      setRecords(items); setRecordsOwner(owner);
    }).catch((failure) => {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Vakalar yüklenemedi. Lütfen tekrar deneyin.');
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [open, visible, owner, scopeVersion, refresh]);

  useEffect(() => {
    if (mobile && open && visible && dialog.current && !dialog.current.open) dialog.current.showModal();
  }, [mobile, open, visible]);

  function openCase(record: PatientRecord) {
    if (mobile) setOpen(false);
    activatePatientRecord(record);
    navigate(`/case?patient=${encodeURIComponent(record.id)}&step=summary`);
  }

  const filtered = (recordsOwner === owner ? records : []).filter((record) => caseNameMatches(record, query));
  const contents = <>
    <div className="shrink-0 space-y-2 px-1 pb-3">
      <p className="text-xs font-semibold text-slate-500">Kayıtlı Vakalar</p>
      <label className="sr-only" htmlFor={`${id}-search`}>Vaka adı ara</label>
      <input id={`${id}-search`} type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Vaka adı ara..." className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400" />
      {loading ? <p role="status" className="text-xs text-slate-500">Vakalar yükleniyor…</p> : null}
      {error ? <div role="alert" className="text-xs text-red-700">{error}<button type="button" onClick={() => setRefresh((value) => value + 1)} className="mt-1 block font-semibold underline">Yeniden dene</button></div> : null}
    </div>
    <div aria-label="Kayıtlı vaka listesi" className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain px-1 pb-2">
      {filtered.map((record) => <CaseHistoryRow key={record.id} compact record={record} active={getActivePatientId() === record.id} onOpen={openCase}
        onRenamed={(renamed) => setRecords((current) => current.map((item) => item.id === renamed.id ? renamed : item))} />)}
      {!loading && !error && !filtered.length ? <p className="py-3 text-xs text-slate-500">{query.trim() ? 'Eşleşen vaka bulunamadı.' : 'Henüz kayıtlı vaka yok.'}</p> : null}
    </div>
    <Link to="/case-archive" onClick={() => { if (mobile) setOpen(false); }} className="shrink-0 border-t border-slate-100 px-1 pt-2 text-xs text-slate-500 hover:text-blue-700">Arşiv ayrıntıları</Link>
  </>;

  return <div className={mobile ? 'contents' : 'flex min-h-0 flex-1 flex-col'}>
    <button type="button" aria-expanded={open && visible} aria-controls={`${id}-cases`} onClick={() => setOpen((value) => !value)}
      className={`${mobile ? 'flex flex-col items-center justify-center rounded-2xl px-2 py-2.5 text-[11px] font-semibold' : 'flex shrink-0 items-center gap-3 rounded-2xl px-3 py-3 text-left text-sm font-medium'} ${open && visible ? 'bg-slate-950 text-white' : 'text-slate-500 hover:bg-slate-100'}`}>
      <span aria-hidden="true" className={mobile ? 'text-lg leading-none' : 'grid h-7 w-7 place-items-center text-base'}>↺</span>
      <span className={mobile ? 'mt-1' : 'flex-1'}>Geçmiş Vakalar</span>
      {!mobile ? <span aria-hidden="true">{open ? '▾' : '▸'}</span> : null}
    </button>
    {open && visible && !mobile ? <div id={`${id}-cases`} className="mt-2 flex min-h-0 flex-1 flex-col">{contents}</div> : null}
    {open && visible && mobile ? <dialog ref={dialog} id={`${id}-cases`} aria-labelledby={`${id}-title`} onCancel={() => setOpen(false)} onClose={() => setOpen(false)}
      onClick={(event) => { if (event.target === event.currentTarget) setOpen(false); }}
      className="fixed inset-0 m-auto h-[75dvh] max-h-[640px] w-[calc(100%-2rem)] max-w-md rounded-3xl border border-slate-200 bg-white p-5 shadow-xl backdrop:bg-slate-950/30">
      <div className="flex h-full min-h-0 flex-col">
        <div className="mb-4 flex shrink-0 items-center justify-between gap-3"><h2 id={`${id}-title`} className="text-lg font-semibold">Geçmiş Vakalar</h2><button type="button" aria-label="Geçmiş vakaları kapat" onClick={() => setOpen(false)} className="rounded-lg px-3 py-2 text-slate-500">✕</button></div>
        {contents}
      </div>
    </dialog> : null}
  </div>;
}
