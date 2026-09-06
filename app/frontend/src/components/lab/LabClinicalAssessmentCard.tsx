import type {
  DerivedLabMetric,
  LabClinicalAssessment,
} from '../../services/labAnalysisClient';

type Props = {
  assessment: LabClinicalAssessment | null | undefined;
  metrics: DerivedLabMetric[] | null | undefined;
};

function metricValue(metric: DerivedLabMetric) {
  const numeric = Number(metric.value);
  if (!Number.isFinite(numeric)) return String(metric.value);
  return new Intl.NumberFormat('tr-TR', {
    maximumFractionDigits: metric.code === 'fib4' ? 2 : 1,
  }).format(numeric);
}

function severityClass(severity: string) {
  if (severity === 'critical') return 'border-red-300 bg-red-100 text-red-900';
  if (severity === 'high') return 'border-rose-200 bg-rose-50 text-rose-900';
  if (severity === 'moderate') return 'border-amber-200 bg-amber-50 text-amber-900';
  return 'border-blue-200 bg-blue-50 text-blue-900';
}

function severityLabel(severity: string) {
  if (severity === 'critical') return 'KRİTİK';
  if (severity === 'high') return 'YÜKSEK ÖNCELİK';
  if (severity === 'moderate') return 'DİKKAT';
  return 'BİLGİ';
}

export default function LabClinicalAssessmentCard({ assessment, metrics }: Props) {
  if (!assessment && (!metrics || metrics.length === 0)) return null;

  return (
    <section className="overflow-hidden rounded-2xl border border-cyan-200 bg-white shadow-sm">
      <div className="border-b border-cyan-100 bg-gradient-to-r from-cyan-50 to-blue-50 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-cyan-700">
              AI Klinik Değerlendirme · KKDS
            </p>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">
              {assessment?.headline ?? 'Native C++ klinik hesaplamaları'}
            </h2>
          </div>
          <span className="rounded-full border border-cyan-200 bg-white px-3 py-1 text-xs font-semibold text-cyan-800">
            {assessment?.synthesis_source === 'deterministic_fallback'
              ? 'C++ doğrulamalı yedek özet'
              : 'Astra + Native C++'}
          </span>
        </div>
        {assessment?.overview ? (
          <p className="mt-3 max-w-5xl text-sm leading-6 text-slate-600">
            {assessment.overview}
          </p>
        ) : null}
      </div>

      <div className="space-y-6 p-5">
        {assessment?.narrative_tr ? (
          <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-5">
            <p className="whitespace-pre-wrap text-[15px] leading-7 text-slate-800">
              {assessment.narrative_tr}
            </p>
          </div>
        ) : null}

        {metrics && metrics.length > 0 ? (
          <div>
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-slate-950">C++ ile hesaplanan metrikler</h3>
              <span className="text-xs font-medium text-slate-500">AI tarafından yeniden hesaplanmaz</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {metrics.map((metric) => (
                <div key={metric.code} className="rounded-xl border border-slate-200 bg-white p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {metric.name}
                  </p>
                  <p className="mt-2 text-2xl font-semibold text-slate-950">
                    {metricValue(metric)}{' '}
                    <span className="text-sm font-medium text-slate-500">{metric.unit}</span>
                  </p>
                  {metric.note ? (
                    <p className="mt-2 text-xs leading-5 text-slate-500">{metric.note}</p>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {assessment?.priority_findings?.length ? (
          <div>
            <h3 className="mb-3 text-sm font-semibold text-slate-950">Öncelikli bulgular</h3>
            <div className="grid gap-3 lg:grid-cols-2">
              {assessment.priority_findings.map((finding, index) => (
                <article key={`${finding.title}-${index}`} className={`rounded-xl border p-4 ${severityClass(finding.severity)}`}>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <h4 className="font-semibold">{finding.title}</h4>
                    <span className="rounded-full border border-current/20 bg-white/60 px-2 py-0.5 text-[10px] font-bold tracking-wide">
                      {severityLabel(finding.severity)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-6">{finding.summary}</p>
                  {finding.evidence.length > 0 ? (
                    <p className="mt-2 text-xs leading-5 opacity-80">
                      Kanıt: {finding.evidence.join(' · ')}
                    </p>
                  ) : null}
                </article>
              ))}
            </div>
          </div>
        ) : null}

        {assessment?.priority_actions?.length ? (
          <div className="rounded-xl border border-violet-200 bg-violet-50 p-4">
            <h3 className="text-sm font-semibold text-violet-950">Öncelik sırası / takip</h3>
            <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6 text-violet-900">
              {assessment.priority_actions.map((action, index) => (
                <li key={`${action}-${index}`}>{action}</li>
              ))}
            </ol>
          </div>
        ) : null}

        {assessment?.reassuring_findings?.length ? (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
            <h3 className="text-sm font-semibold text-emerald-950">Rahatlatıcı / normal görünen bulgular</h3>
            <div className="mt-2 flex flex-wrap gap-2">
              {assessment.reassuring_findings.map((finding, index) => (
                <span key={`${finding}-${index}`} className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-emerald-800">
                  ✓ {finding}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        <p className="text-xs leading-5 text-slate-500">
          Bu bölüm klinik karar desteğidir; kesin tanı veya tedavi kararı değildir. Kaynak laboratuvar raporu ve hekim değerlendirmesi esastır.
        </p>
      </div>
    </section>
  );
}
