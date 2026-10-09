import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { caseDisplayName } from '../../services/caseManagement';
import { activatePatientRecord, getActivePatientId, getPatientRecord, type PatientRecord } from '../../services/patientClient';
import { capturePatientScope, isCurrentPatientScope } from '../../services/patientScope';

/** Reuse the existing persisted active-case pointer; verify it with the server. */
export default function LastCaseResume() {
  const [record, setRecord] = useState<PatientRecord | null>(null);
  useEffect(() => {
    const id = getActivePatientId();
    if (!id) return;
    const scope = capturePatientScope();
    const controller = new AbortController();
    void getPatientRecord(id, controller.signal).then((patient) => {
      if (!controller.signal.aborted && isCurrentPatientScope(scope)) setRecord(patient);
    }).catch(() => { /* An inaccessible/deleted case is never offered as a draft. */ });
    return () => controller.abort();
  }, []);
  if (!record) return null;
  return <section className="flex flex-wrap items-center justify-between gap-3 rounded-[28px] border border-blue-200 bg-blue-50 p-5">
    <p className="text-sm text-blue-900">Son çalışılan vaka: <strong>{caseDisplayName(record)}</strong></p>
    <Link to={`/case?patient=${encodeURIComponent(record.id)}&step=summary`} onClick={() => activatePatientRecord(record)} className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">Vakaya devam et</Link>
  </section>;
}
