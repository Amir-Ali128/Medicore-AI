type Metadata = Record<string, unknown>;

type DerivedScore = {
  code: string;
  name: string;
  status: 'computed' | 'unavailable' | string;
  value: number | null;
  band: string;
  formula: string;
  inputs?: Record<string, unknown>;
  thresholds?: string | null;
  missing?: string[];
  note?: string | null;
  source_reference?: string | null;
};

type CrossCheck = {
  code: string;
  severity: 'review' | 'context' | string;
  title: string;
  message: string;
  inputs?: Record<string, unknown>;
};

type TemporalContext = {
  laboratory_date?: string | null;
  ultrasound_date?: string | null;
  gap_days?: number | null;
  warning?: string | null;
};

type RiskDetail = {
  source?: string;
  flag?: string;
  title?: string;
  detail?: string;
  rule?: string;
};

type RiskExplanation = {
  displayed_risk?: number;
  deterministic_baseline?: number;
  scale?: Record<string, string>;
  flags?: RiskDetail[];
  all_flag_codes?: string[];
  note?: string;
};

type AlreadyPerformedStudy = {
  code?: string;
  name?: string;
  performed_name?: string;
  date?: string | null;
  rationale?: string;
};

type TrendDelta = {
  name?: string;
  previous?: number;
  current?: number;
  absolute_difference?: number | null;
  percentage_difference?: number | null;
  time_difference_days?: number | null;
  direction?: 'up' | 'down' | 'same' | string;
};

function objectArray<T>(value: unknown): T[] {
  return Array.isArray(value)
    ? value.filter((item): item is T => typeof item === 'object' && item !== null)
    : [];
}

function objectValue<T extends object>(value: unknown): T | null {
  return typeof value === 'object' && value !== null ? (value as T) : null;
}

function formatDate(value: string | null | undefined) {
  if (!value) return 'Tarih bilinmiyor';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('tr-TR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(parsed);
}

function inputText(inputs: Record<string, unknown> | undefined) {
  if (!inputs) return '';
  return Object.entries(inputs)
    .map(([key, value]) => `${key}=${String(value)}`)
    .join(' · ');
}

function bandClass(band: string) {
  const normalized = band.toLocaleLowerCase('tr-TR');
  if (normalized.includes('yüksek')) return 'border-rose-200 bg-rose-50 text-rose-700';
  if (normalized.includes('düşük')) return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (normalized.includes('belirsiz') || normalized.includes('ara')) {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }
  return 'border-slate-200 bg-slate-50 text-slate-700';
}

function directionGlyph(direction: TrendDelta['direction']) {
  if (direction === 'up') return '↑';
  if (direction === 'down') return '↓';
  return '→';
}

export default function ClinicalRuleDetails({ metadata }: { metadata: Metadata }) {
  const scores = objectArray<DerivedScore>(metadata.deterministic_scores);
  const crossChecks = objectArray<CrossCheck>(metadata.cross_consistency);
  const reviewChecks = crossChecks.filter((item) => item.severity === 'review');
  const contextChecks = crossChecks.filter((item) => item.severity === 'context');
  const temporal = objectValue<TemporalContext>(metadata.temporal_context);
  const risk = objectValue<RiskExplanation>(metadata.risk_explanation);
  const alreadyPerformed = objectArray<AlreadyPerformedStudy>(metadata.already_performed_studies);
  const trendDeltas = objectArray<TrendDelta>(metadata.trend_deltas);

  const hasContent =
    scores.length > 0 ||
    crossChecks.length > 0 ||
    Boolean(temporal?.warning) ||
    Boolean(risk) ||
    alreadyPerformed.length > 0 ||
    trendDeltas.length > 0;

  if (!hasContent) return null;

  return (
    <div className="mt-4 space-y-4">
      {temporal?.warning ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm font-semibold text-amber-950">Zamansal veri uyarısı</p>
          <p className="mt-1 text-sm leading-6 text-amber-900">{temporal.warning}</p>
          <p className="mt-2 text-xs text-amber-800">
            Laboratuvar: {formatDate(temporal.laboratory_date)} · Ultrason: {formatDate(temporal.ultrasound_date)}
          </p>
        </div>
      ) : null}

      {risk ? (
        <details className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <summary className="cursor-pointer text-sm font-semibold text-slate-950">
            Risk skoru nasıl oluştu?
          </summary>
          <div className="mt-3 space-y-3">
            <p className="text-xs leading-5 text-slate-600">
              Gösterilen risk: <strong>{risk.displayed_risk ?? '—'}/3</strong> · Deterministik başlangıç düzeyi:{' '}
              <strong>{risk.deterministic_baseline ?? '—'}/3</strong>
            </p>
            {risk.scale ? (
              <div className="grid gap-2 text-xs sm:grid-cols-3">
                {Object.entries(risk.scale).map(([level, text]) => (
                  <div key={level} className="rounded-lg border border-slate-200 bg-white p-2.5 text-slate-600">
                    <span className="font-semibold text-slate-900">{level}/3</span> · {text}
                  </div>
                ))}
              </div>
            ) : null}
            {Array.isArray(risk.flags) && risk.flags.length > 0 ? (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Risk değerlendirmesine giren sinyaller
                </p>
                <ul className="mt-2 space-y-2">
                  {risk.flags.map((item, index) => (
                    <li key={`${item.flag ?? item.title}-${index}`} className="rounded-lg border border-slate-200 bg-white p-3">
                      <p className="text-xs font-semibold text-slate-900">{item.title ?? item.flag}</p>
                      {item.detail ? <p className="mt-1 text-xs leading-5 text-slate-600">{item.detail}</p> : null}
                      {item.rule ? <p className="mt-1 text-[11px] text-slate-500">Kural: {item.rule}</p> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {risk.note ? <p className="text-[11px] leading-5 text-slate-500">{risk.note}</p> : null}
          </div>
        </details>
      ) : null}

      {scores.length > 0 ? (
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <div>
            <h4 className="text-sm font-semibold text-slate-950">Deterministik klinik skorlar</h4>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              Formül ve kullanılan değerler görünür tutulur. Eksik veri varsa skor tahmin edilmez.
            </p>
          </div>
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            {scores.map((score) => (
              <div key={score.code} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-950">{score.name}</p>
                    <p className="mt-1 text-xs text-slate-500">{score.formula}</p>
                  </div>
                  <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${bandClass(score.band)}`}>
                    {score.status === 'computed' ? score.band : 'Hesaplanamadı'}
                  </span>
                </div>
                {score.status === 'computed' ? (
                  <>
                    <p className="mt-3 text-lg font-semibold text-slate-950">{score.value}</p>
                    {inputText(score.inputs) ? (
                      <p className="mt-2 text-xs leading-5 text-slate-600">Kullanılan değerler: {inputText(score.inputs)}</p>
                    ) : null}
                    {score.thresholds ? (
                      <p className="mt-1 text-xs leading-5 text-slate-600">Bantlar: {score.thresholds}</p>
                    ) : null}
                    {score.source_reference ? (
                      <p className="mt-2 text-[11px] leading-4 text-slate-500">Referans: {score.source_reference}</p>
                    ) : null}
                  </>
                ) : (
                  <p className="mt-3 text-xs leading-5 text-slate-600">
                    Eksik: {Array.isArray(score.missing) && score.missing.length > 0 ? score.missing.join(', ') : 'gerekli parametre'}
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {reviewChecks.length > 0 ? (
        <section className="rounded-xl border border-amber-200 bg-amber-50/60 p-4">
          <h4 className="text-sm font-semibold text-amber-950">Çapraz tutarlılık uyarıları</h4>
          <p className="mt-1 text-xs leading-5 text-amber-900">
            Bunlar tanı değildir; iki veya daha fazla sonucun birlikte beklenmedik görünmesi nedeniyle doğrulama sinyalidir.
          </p>
          <ul className="mt-3 space-y-2">
            {reviewChecks.map((check) => (
              <li key={check.code} className="rounded-lg border border-amber-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-900">{check.title}</p>
                <p className="mt-1 text-xs leading-5 text-slate-600">{check.message}</p>
                {inputText(check.inputs) ? <p className="mt-1 text-[11px] text-slate-500">{inputText(check.inputs)}</p> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {contextChecks.length > 0 ? (
        <section className="rounded-xl border border-blue-100 bg-blue-50/50 p-4">
          <h4 className="text-sm font-semibold text-blue-950">Çapraz bağlam</h4>
          <ul className="mt-2 space-y-2">
            {contextChecks.map((check) => (
              <li key={check.code} className="text-xs leading-5 text-slate-700">
                <strong>{check.title}:</strong> {check.message}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {trendDeltas.length > 0 ? (
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h4 className="text-sm font-semibold text-slate-950">Önceki sonuçlara göre değişim</h4>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {trendDeltas.map((item, index) => (
              <div key={`${item.name}-${index}`} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs font-semibold text-slate-900">{directionGlyph(item.direction)} {item.name}</p>
                <p className="mt-1 text-xs text-slate-600">
                  {item.previous} → {item.current}
                  {typeof item.percentage_difference === 'number' ? ` · %${item.percentage_difference.toFixed(1)}` : ''}
                </p>
                {item.time_difference_days != null ? (
                  <p className="mt-1 text-[11px] text-slate-500">{item.time_difference_days} gün arayla</p>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {alreadyPerformed.length > 0 ? (
        <section className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
          <h4 className="text-sm font-semibold text-emerald-950">Zaten yapılmış tetkikler</h4>
          <p className="mt-1 text-xs leading-5 text-emerald-900">
            Bunlar yeni öneri listesinden otomatik çıkarıldı; mevcut vaka bağlamı için burada tutuluyor.
          </p>
          <ul className="mt-3 space-y-2">
            {alreadyPerformed.map((study, index) => (
              <li key={`${study.code ?? study.name}-${index}`} className="rounded-lg border border-emerald-200 bg-white p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-slate-900">{study.performed_name ?? study.name}</span>
                  <span className="text-[11px] text-slate-500">{formatDate(study.date)}</span>
                </div>
                {study.rationale ? <p className="mt-1 text-xs leading-5 text-slate-600">{study.rationale}</p> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
