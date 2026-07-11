import type { DexaMetric } from '../../services/radiologyClient';

const SITE_LABELS: Record<string, string> = {
  LUMBAR_SPINE_L1_L4: 'Lomber omurga L1-L4',
  FEMORAL_NECK: 'Femur boynu',
  TOTAL_HIP: 'Total kalça',
  FOREARM_33_RADIUS: 'Ön kol / %33 radius',
  WHOLE_BODY: 'Tüm vücut',
  UNSPECIFIED: 'Bölge belirtilmemiş',
};

const T_BAND_LABELS: Record<string, string> = {
  normal_range: 'Normal aralık bandı',
  low_bone_mass_range: 'Düşük kemik kütlesi bandı',
  osteoporosis_range: 'Osteoporoz eşiği bandı',
};

const Z_BAND_LABELS: Record<string, string> = {
  below_expected_for_age: 'Yaşa göre beklenen aralığın altında',
  within_expected_for_age: 'Yaşa göre beklenen aralıkta',
};

function bandClassName(value: string | null) {
  if (value === 'osteoporosis_range' || value === 'below_expected_for_age') {
    return 'border-red-200 bg-red-50 text-red-900';
  }
  if (value === 'low_bone_mass_range') {
    return 'border-amber-200 bg-amber-50 text-amber-900';
  }
  return 'border-emerald-200 bg-emerald-50 text-emerald-900';
}

export default function DexaMetricsPanel({ metrics }: { metrics: DexaMetric[] }) {
  if (metrics.length === 0) return null;

  return (
    <section className="rounded-xl border border-indigo-200 bg-indigo-50/40 p-5">
      <div>
        <p className="text-xs font-bold uppercase tracking-wide text-indigo-700">
          DEXA / DXA yapılandırılmış sonuçları
        </p>
        <h3 className="mt-2 text-lg font-semibold text-slate-950">
          BMD, T-score ve Z-score
        </h3>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Skor bantları yalnızca hekim incelemesini kolaylaştıran yardımcı işaretlerdir;
          tek başına tanı değildir.
        </p>
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-2">
        {metrics.map((metric, index) => (
          <article
            key={`${metric.site}-${metric.bmd}-${metric.t_score}-${index}`}
            className="rounded-xl border border-slate-200 bg-white p-5"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-slate-950">
                  {SITE_LABELS[metric.site] ?? metric.site}
                </p>
                <p className="mt-1 text-xs text-slate-500">Ölçüm satırı {index + 1}</p>
              </div>
              {metric.report_classification ? (
                <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-800">
                  Raporda: {metric.report_classification}
                </span>
              ) : null}
            </div>

            <div className="mt-4 grid grid-cols-3 gap-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p className="text-[11px] font-semibold uppercase text-slate-500">BMD</p>
                <p className="mt-1 font-semibold text-slate-950">
                  {metric.bmd ?? '-'} {metric.bmd_unit ?? ''}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p className="text-[11px] font-semibold uppercase text-slate-500">T-score</p>
                <p className="mt-1 font-semibold text-slate-950">{metric.t_score ?? '-'}</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p className="text-[11px] font-semibold uppercase text-slate-500">Z-score</p>
                <p className="mt-1 font-semibold text-slate-950">{metric.z_score ?? '-'}</p>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              {metric.t_score_band ? (
                <span className={`rounded-lg border px-2.5 py-1.5 text-xs font-semibold ${bandClassName(metric.t_score_band)}`}>
                  T: {T_BAND_LABELS[metric.t_score_band] ?? metric.t_score_band}
                </span>
              ) : null}
              {metric.z_score_band ? (
                <span className={`rounded-lg border px-2.5 py-1.5 text-xs font-semibold ${bandClassName(metric.z_score_band)}`}>
                  Z: {Z_BAND_LABELS[metric.z_score_band] ?? metric.z_score_band}
                </span>
              ) : null}
            </div>

            <p className="mt-4 text-xs leading-5 text-slate-500">{metric.context}</p>
          </article>
        ))}
      </div>

      <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">
        T-score ve Z-score yorumu yaş, cinsiyet, menopoz durumu, ölçüm bölgesi,
        cihaz referans verisi, görüntü kalitesi ve klinik bağlama göre değişebilir.
        Kesin değerlendirme orijinal rapor ve hekim incelemesiyle yapılmalıdır.
      </p>
    </section>
  );
}
