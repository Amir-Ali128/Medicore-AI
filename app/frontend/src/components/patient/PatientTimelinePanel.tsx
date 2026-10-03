import { useEffect, useState } from 'react';
import ClinicalHistorySummary from '../clinical/ClinicalHistorySummary';
import { formatVitals } from '../../services/clinicalRecord';
import { getPatientHealthTimeline } from '../../services/patientTimelineClient';
import { timelineReportLabel, type PatientHealthTimeline, type PatientTimelineEntry } from '../../services/patientTimelineGrouping';

function displayDay(value: string | null) {
  if (!value) return 'Tarihi belirtilmemiş kayıtlar';
  return new Intl.DateTimeFormat('tr-TR', { dateStyle: 'long' }).format(new Date(`${value}T12:00:00`));
}

function Entry({ entry }: { entry: PatientTimelineEntry }) {
  const fallbackDate = ['created_at', 'clinical_recorded_at', 'vitals_recorded_at', 'clinical_context_recorded_at'].includes(entry.date_source);
  const title = entry.kind === 'report' ? timelineReportLabel(entry.inferred_report_type) : entry.title;
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold text-slate-900">{title}</h3>
        {fallbackDate ? <span className="text-xs text-slate-500">Kayıt tarihi</span> : null}
      </div>
      {entry.file_name ? <p className="mt-1 break-words text-xs text-slate-500">{entry.file_name}</p> : null}
      {entry.kind === 'laboratory' || entry.kind === 'urine_laboratory' ? (
        <details className="mt-3" open={entry.results.length <= 6}>
          <summary className="cursor-pointer text-sm font-medium text-blue-700">Tüm sonuçları göster ({entry.results.length})</summary>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-xs text-slate-500">
                <tr><th className="py-2 pr-4">Test</th><th className="py-2 pr-4">Sonuç</th><th className="py-2 pr-4">Birim</th><th className="py-2">Referans</th></tr>
              </thead>
              <tbody>
                {entry.results.map((result) => (
                  <tr key={result.id} className="border-b border-slate-100 last:border-0">
                    <td className="py-2 pr-4 font-medium">{result.test_name}</td>
                    <td className="py-2 pr-4">{result.value ?? '—'}</td>
                    <td className="py-2 pr-4">{result.unit || '—'}</td>
                    <td className="py-2">{result.reference_text || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
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
  return (
    <div className="space-y-7">
      {timeline.groups.map((group) => (
        <section key={group.date ?? 'undated'}>
          <h2 className="mb-3 text-lg font-semibold text-slate-950">{displayDay(group.date)}</h2>
          <div className="space-y-3 border-l-2 border-blue-100 pl-4">
            {group.entries.map((entry) => <Entry key={entry.id} entry={entry} />)}
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
