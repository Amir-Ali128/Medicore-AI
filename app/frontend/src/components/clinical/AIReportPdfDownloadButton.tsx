import { useEffect, useRef, useState } from 'react';
import { capturePatientScope, isCurrentPatientScope } from '../../services/patientScope';
import { exportCurrentAIReport, PDF_EXPORT_ERROR } from '../../services/aiReportPdf';

type Props = { reportText?: string | null; caseId?: string | null; protocolNo?: string | null; reportWarning?: string };

export default function AIReportPdfDownloadButton(props: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const current = useRef(props);
  const mounted = useRef(true);
  const pending = useRef(false);
  current.current = props;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { setError(''); }, [props.reportText, props.caseId, props.protocolNo, props.reportWarning]);

  async function download() {
    if (!props.reportText?.trim() || pending.current) return;
    const snapshot = { ...props, reportText: props.reportText };
    const scope = capturePatientScope();
    const isCurrent = () => mounted.current && isCurrentPatientScope(scope)
      && current.current.reportText === snapshot.reportText && current.current.caseId === snapshot.caseId
      && current.current.protocolNo === snapshot.protocolNo && current.current.reportWarning === snapshot.reportWarning;
    pending.current = true; setBusy(true); setError('');
    try {
      await exportCurrentAIReport(snapshot, { isCurrent });
    } catch {
      if (isCurrent()) setError(PDF_EXPORT_ERROR);
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  return <div>
    <button type="button" onClick={download} disabled={busy || !props.reportText?.trim()} aria-busy={busy}
      className="rounded-2xl border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-800 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
      {busy ? 'PDF hazırlanıyor…' : 'PDF İndir'}
    </button>
    {error ? <p role="alert" className="mt-2 max-w-md text-sm text-red-700">{error}</p> : null}
  </div>;
}
