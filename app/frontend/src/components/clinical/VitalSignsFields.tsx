import { VITAL_FIELDS, type VitalDraft } from '../../services/clinicalRecord';

export default function VitalSignsFields({ values, onChange }: {
  values: VitalDraft;
  onChange: (values: VitalDraft) => void;
}) {
  return (
    <fieldset className="mt-6 rounded-3xl border border-slate-200 p-5">
      <legend className="px-2 text-lg font-semibold text-slate-950">Vital Bulgular</legend>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {VITAL_FIELDS.map(({ key, label, unit, min, max, step }) => (
          <label key={key} className="text-xs font-semibold text-slate-500">
            {label} <span className="font-normal">({unit})</span>
            <input
              type="number"
              inputMode="decimal"
              value={values[key]}
              min={min}
              max={max}
              step={step}
              onChange={(event) => onChange({ ...values, [key]: event.target.value })}
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-normal text-slate-950 outline-none focus:border-blue-400"
            />
          </label>
        ))}
      </div>
    </fieldset>
  );
}
