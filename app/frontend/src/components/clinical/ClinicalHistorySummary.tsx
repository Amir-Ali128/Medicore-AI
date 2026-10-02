import type { ClinicalContext } from '../../services/simpleCaseClient';
import { clinicalRows, formatVitals } from '../../services/clinicalRecord';

export default function ClinicalHistorySummary({ clinical }: { clinical: ClinicalContext }) {
  const rows = clinicalRows(clinical);
  const vitals = formatVitals(clinical.vital_signs);
  if (!rows.length && !vitals.length) return <p className="mt-3 text-sm text-slate-500">Henüz klinik bilgi eklenmedi.</p>;
  return (
    <div className="mt-3 space-y-3">
      {rows.map(([label, value]) => (
        <div key={label} className="text-xs leading-5 text-slate-700">
          <p className="font-semibold">{label}</p>
          <p className="whitespace-pre-line break-words">{value}</p>
        </div>
      ))}
      {vitals.length > 0 ? (
        <div className="text-xs leading-5 text-slate-700">
          <p className="font-semibold">Vital Bulgular</p>
          <p>{vitals.join(' · ')}</p>
        </div>
      ) : null}
    </div>
  );
}
