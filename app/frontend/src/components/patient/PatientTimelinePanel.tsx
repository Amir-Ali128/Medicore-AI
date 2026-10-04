import { useEffect, useState } from 'react';
import ClinicalHistorySummary from '../clinical/ClinicalHistorySummary';
import { formatVitals } from '../../services/clinicalRecord';
import { getPatientHealthTimeline } from '../../services/patientTimelineClient';
import { timelineReportLabel, type PatientHealthTimeline, type PatientTimelineEntry, type TimelineDates, type TimelineLabValue } from '../../services/patientTimelineGrouping';

function displayDay(value: string | null) {
  if (!value) return 'Tarihi belirtilmemiş kayıtlar';
  return new Intl.DateTimeFormat('tr-TR', { dateStyle: 'long' }).format(new Date(`${value}T12:00:00`));
}

const FALLBACK_DATE_SOURCES = ['uploaded_at', 'created_at', 'clinical_recorded_at', 'vitals_recorded_at', 'clinical_context_recorded_at'];

function dateLabels(dates: TimelineDates, entry: PatientTimelineEntry) {
  const labels: string[] = [];
  const add = (label: string, value: string | null | undefined) => {
    if (value && /^\d{4}-\d{2}-\d{2}/.test(value)) labels.push(`${label}: ${displayDay(value.slice(0, 10))}`);
  };
  if (dates.specimen_date) add('Örnek', dates.specimen_date);
  else if (dates.event_date) {
    const fallback = FALLBACK_DATE_SOURCES.includes(entry.date_source);
    const duplicatesUpload = fallback && dates.uploaded_at?.slice(0, 10) === dates.event_date.slice(0, 10);
    if (!duplicatesUpload) {
      const label = fallback ? 'Kayıt' : ['exam_date', 'examination_date'].includes(entry.date_source) ? 'Muayene' : entry.date_source === 'consultation_date' ? 'Konsültasyon' : 'Klinik olay';
      add(label, dates.event_date);
    }
  }
  add('Sonuç', dates.result_date);
  add('Belge', dates.document_date);
  add('Yükleme', dates.uploaded_at);
  return labels;
}

const STATUS_LABELS = { LOW: 'Düşük', NORMAL: 'Normal', HIGH: 'Yüksek', UNKNOWN: 'Değerlendirilemedi' };
const STATUS_STYLES = { LOW: 'bg-amber-50 text-amber-800', NORMAL: 'bg-emerald-50 text-emerald-800', HIGH: 'bg-red-50 text-red-700', UNKNOWN: 'bg-slate-100 text-slate-600' };

function LabResults({ entry, results }: { entry: PatientTimelineEntry; results: TimelineLabValue[] }) {
  const entryDates = dateLabels(entry, entry).join(' · ');
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-xs text-slate-500">
          <tr><th className="py-2 pr-4">Test</th><th className="py-2 pr-4">Sonuç</th><th className="py-2 pr-4">Birim</th><th className="py-2 pr-4">Referans</th><th className="py-2">Durum</th></tr>
        </thead>
        <tbody>
          {results.map((result) => {
            const status = result.status === 'LOW' || result.status === 'NORMAL' || result.status === 'HIGH' ? result.status : 'UNKNOWN';
            const dates = dateLabels(result, entry).join(' · ');
            return (
              <tr key={result.id} className="border-b border-slate-100 last:border-0">
                <td className="py-2 pr-4 font-medium">{result.test_name}{dates && dates !== entryDates ? <span className="mt-1 block text-xs font-normal text-slate-500">{dates}</span> : null}</td>
                <td className="py-2 pr-4">{result.value ?? '—'}</td>
                <td className="py-2 pr-4">{result.unit || '—'}</td>
                <td className="py-2 pr-4">{result.raw_reference || result.reference_text || '—'}</td>
                <td className="py-2"><span className={`rounded-full px-2 py-1 text-xs ${STATUS_STYLES[status]}`}>{STATUS_LABELS[status]}</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

type ResultSource = { entry: PatientTimelineEntry; result: TimelineLabValue };
const resultKey = (entry: PatientTimelineEntry, id: string) => `${entry.patient_id}:${entry.source_type}:${entry.source_id}:${id}`;

function Entry({ entry, resultSources }: { entry: PatientTimelineEntry; resultSources: Map<string, ResultSource> }) {
  const fallbackDate = FALLBACK_DATE_SOURCES.includes(entry.date_source);
  const title = entry.kind === 'report' ? timelineReportLabel(entry.inferred_report_type) : entry.title;
  const dates = dateLabels(entry, entry).join(' · ');
  const lateResults = entry.kind === 'lab_result_available'
    ? [...new Set(entry.result_ids ?? [])].flatMap((id) => { const source = resultSources.get(resultKey(entry, id)); return source ? [source] : []; })
    : [];
  return (
    <article id={`timeline-${entry.id}`} className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold text-slate-900">{title}</h3>
        {fallbackDate ? <span className="text-xs text-slate-500">Kayıt tarihi</span> : null}
      </div>
      {entry.file_name ? <p className="mt-1 break-words text-xs text-slate-500">{entry.file_name}</p> : null}
      {dates ? <p className="mt-2 text-xs leading-5 text-slate-600">{dates}</p> : null}
      {entry.kind === 'laboratory' || entry.kind === 'urine_laboratory' ? (
        <details className="mt-3" open={entry.results.length <= 6}>
          <summary className="cursor-pointer text-sm font-medium text-blue-700">Tüm sonuçları göster ({entry.results.length})</summary>
          <LabResults entry={entry} results={entry.results} />
        </details>
      ) : null}
      {entry.kind === 'lab_result_available' ? (
        <div className="mt-3">
          <p className="text-sm text-slate-600">İlgili laboratuvar kaydının sonuçları bu tarihte kullanılabilir hale geldi.</p>
          {lateResults.length ? <>
            <LabResults entry={entry} results={lateResults.map(({ result }) => result)} />
            <div className="mt-3 flex flex-wrap gap-3">
              {[...new Map(lateResults.map(({ entry: source }) => [source.id, source])).values()].map((source) => (
                <button key={source.id} type="button" aria-controls={`timeline-${source.id}`} onClick={() => document.getElementById(`timeline-${source.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })} className="text-sm font-medium text-blue-700 underline">Laboratuvar kaydını göster</button>
              ))}
            </div>
          </> : <p className="mt-2 text-sm text-slate-500">Sonuç ayrıntıları ilgili laboratuvar kaydında bulunur.</p>}
        </div>
      ) : null}
      {entry.kind === 'report' ? (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-medium text-blue-700">Raporu Gör</summary>
          <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{entry.report_text || entry.summary || 'Bu kayıtta rapor metni bulunmuyor.'}</p>
        </details>
      ) : null}
      {entry.kind === 'clinical' && entry.clinical ? <ClinicalHistorySummary clinical={entry.clinical} /> : null}
      {entry.kind === 'vital_signs' ? <p className="mt-3 text-sm leading-6 text-slate-700">{formatVitals(entry.vital_signs).join(' · ')}</p> : null}
    </article>
  );
}

export function PatientTimelineContent({ timeline }: { timeline: PatientHealthTimeline }) {
  if (!timeline.groups.length) return <p className="text-sm text-slate-500">Bu hasta için kayıtlı sağlık geçmişi bulunmuyor.</p>;
  const resultSources = new Map<string, ResultSource>();
  for (const group of timeline.groups) {
    for (const entry of group.entries) {
      if (entry.patient_id !== timeline.patient_id || !['laboratory', 'urine_laboratory'].includes(entry.kind)) continue;
      for (const result of entry.results) resultSources.set(resultKey(entry, result.id), { entry, result });
    }
  }
  return (
    <div className="space-y-7">
      {timeline.groups.map((group) => (
        <section key={group.date ?? 'undated'}>
          <h2 className="mb-3 text-lg font-semibold text-slate-950">{displayDay(group.date)}</h2>
          <div className="space-y-3 border-l-2 border-blue-100 pl-4">
            {group.entries.map((entry) => <Entry key={entry.id} entry={entry} resultSources={resultSources} />)}
          </div>
        </section>
      ))}
    </div>
  );
}

export default function PatientTimelinePanel({ patientId }: { patientId: string }) {
  const [state, setState] = useState<{ patientId: string; data: PatientHealthTimeline | null; error: string; loading: boolean }>({ patientId, data: null, error: '', loading: true });
  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    setState({ patientId, data: null, error: '', loading: true });
    void getPatientHealthTimeline(patientId, controller.signal).then((data) => {
      if (!cancelled && !controller.signal.aborted) setState({ patientId, data, error: '', loading: false });
    }).catch((error: unknown) => {
      if (!cancelled && !controller.signal.aborted) setState({ patientId, data: null, error: error instanceof Error ? error.message : 'Hasta geçmişi yüklenemedi.', loading: false });
    });
    return () => { cancelled = true; controller.abort(); };
  }, [patientId]);
  // A prop change hides the old patient's data before the next effect runs.
  if (state.patientId !== patientId || state.loading) return <p className="text-sm text-slate-500" role="status">Hasta geçmişi yükleniyor…</p>;
  if (state.error) return <p className="rounded-2xl bg-red-50 p-4 text-sm text-red-700" role="alert">{state.error}</p>;
  return state.data ? <PatientTimelineContent timeline={state.data} /> : null;
}
