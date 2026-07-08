import type { DoctorInterpretationSummary } from '../services/clinicalInterpreter';

function severityClassName(severity: string) {
  switch (severity) {
    case 'high':
      return 'border-red-200 bg-red-50 text-red-700';
    case 'moderate':
      return 'border-amber-200 bg-amber-50 text-amber-700';
    default:
      return 'border-blue-200 bg-blue-50 text-blue-700';
  }
}

function severityLabel(severity: string) {
  switch (severity) {
    case 'high':
      return 'Öncelikli değerlendirme';
    case 'moderate':
      return 'Klinik değerlendirme';
    default:
      return 'Düşük öncelik';
  }
}

export default function DoctorLanguageSummary({
  summary,
}: {
  summary: DoctorInterpretationSummary;
}) {
  if (summary.items.length === 0) {
    return (
      <div className="rounded-lg border border-emerald-100 bg-emerald-50 p-5">
        <p className="font-semibold text-emerald-800">
          Klinik açıdan öncelikli Düşük/Yüksek sinyal saptanmadı.
        </p>
        <p className="mt-2 text-sm leading-6 text-emerald-700">
          Sonuçlar mevcut referans aralıklarına göre normal sınıflanmış görünüyor.
          Yine de nihai değerlendirme hastanın klinik durumu ile birlikte yapılmalıdır.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold uppercase text-slate-500">
            Düşük / yüksek sinyaller
          </p>
          <p className="mt-2 text-2xl font-semibold text-slate-950">
            {summary.abnormalCount}
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold uppercase text-slate-500">
            Düşük
          </p>
          <p className="mt-2 text-2xl font-semibold text-slate-950">
            {summary.lowCount}
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold uppercase text-slate-500">
            Yüksek
          </p>
          <p className="mt-2 text-2xl font-semibold text-slate-950">
            {summary.highCount}
          </p>
        </div>
      </div>

      <div className="grid gap-4">
        {summary.items.map((item) => (
          <article
            key={item.id}
            className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
          >
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase text-slate-500">
                  {item.system}
                </p>
                <h3 className="mt-1 text-lg font-semibold text-slate-950">
                  {item.title}
                </h3>
              </div>

              <span
                className={`inline-flex w-fit rounded-full border px-3 py-1 text-xs font-semibold ${severityClassName(
                  item.severity,
                )}`}
              >
                {severityLabel(item.severity)}
              </span>
            </div>

            <div className="mt-4 rounded-lg border border-slate-100 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase text-slate-500">
                İlgili markerlar
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {item.markers.map((marker) => (
                  <span
                    key={marker}
                    className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700"
                  >
                    {marker}
                  </span>
                ))}
              </div>
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-3">
              <div>
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Doktor dili yorum
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-700">
                  {item.interpretation}
                </p>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Klinik bağlam
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-700">
                  {item.clinicalContext}
                </p>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase text-slate-500">
                  Hekim aksiyonu
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-700">
                  {item.suggestedDoctorAction}
                </p>
              </div>
            </div>
          </article>
        ))}
      </div>

      <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
        <p className="text-sm leading-6 text-blue-800">{summary.safetyNote}</p>
      </div>
    </div>
  );
}
