import type {
  ClaudeEvaluationHypothesis,
  ClaudePathologicalFinding,
  ClaudeSuggestedTest,
} from '../../services/claudeReviewClient';

type ExtendedFinding = ClaudePathologicalFinding & {
  raw_value?: string | null;
  display_value?: string | null;
  measured_at?: string | null;
  previous_value?: string | null;
  absolute_difference?: string | null;
  percentage_difference?: number | null;
  time_difference_days?: number | null;
  trend_status?: string | null;
};

type ScoreInput = {
  name: string;
  value: number | string | null;
  raw_value?: string | null;
  unit?: string | null;
};

type DerivedScore = {
  code: string;
  label: string;
  status: 'calculated' | 'unavailable' | string;
  value: number | null;
  band: string | null;
  band_label: string | null;
  formula: string;
  inputs: ScoreInput[];
  missing: string[];
  flag?: string | null;
  note?: string | null;
};

type ConsistencyCheck = {
  code: string;
  severity: string;
  kind: string;
  label: string;
  message: string;
  values: ScoreInput[];
};

type AlreadyPerformedTest = ClaudeSuggestedTest & {
  canonical_code?: string | null;
  source?: string | null;
  performed_date?: string | null;
  reason?: string | null;
};

type RiskTrigger = {
  flag: string;
  label: string;
  rule?: string | null;
  parameters?: Array<{
    name?: string;
    value?: number | string | null;
    unit?: string | null;
    reference_min?: number | string | null;
    reference_max?: number | string | null;
  }>;
};

type RiskExplanation = {
  score: number;
  scale_min: number;
  scale_max: number;
  scale_label: string;
  basis: string;
  triggers: RiskTrigger[];
  note?: string | null;
};

type TemporalContext = {
  laboratory_date?: string | null;
  ultrasound_date?: string | null;
  gap_days?: number | null;
  threshold_days?: number | null;
  warning?: boolean;
  message?: string | null;
};

function readStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}

function readPathologicalFindings(value: unknown): ExtendedFinding[] {
  if (!Array.isArray(value)) return [];

  return value.filter((item): item is ExtendedFinding => {
    if (typeof item !== 'object' || item === null) return false;
    const finding = item as Record<string, unknown>;
    return (
      typeof finding.name === 'string' &&
      typeof finding.status === 'string' &&
      typeof finding.status_label === 'string' &&
      typeof finding.display === 'string' &&
      (finding.source === 'laboratory' || finding.source === 'vital')
    );
  });
}

function readSuggestedTests(value: unknown): ClaudeSuggestedTest[] {
  if (!Array.isArray(value)) return [];

  return value
    .filter((item): item is Record<string, unknown> => {
      return typeof item === 'object' && item !== null;
    })
    .map((item) => ({
      name: typeof item.name === 'string' ? item.name : 'Belirtilmemiş tetkik',
      rationale: typeof item.rationale === 'string' ? item.rationale : null,
      priority:
        item.priority === 'routine' ||
        item.priority === 'soon' ||
        item.priority === 'urgent'
          ? item.priority
          : null,
    }));
}

function readAlreadyPerformed(value: unknown): AlreadyPerformedTest[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter(
      (item): item is Record<string, unknown> =>
        typeof item === 'object' && item !== null,
    )
    .map((item) => ({
      name: typeof item.name === 'string' ? item.name : 'Belirtilmemiş tetkik',
      rationale: typeof item.rationale === 'string' ? item.rationale : null,
      priority:
        item.priority === 'routine' ||
        item.priority === 'soon' ||
        item.priority === 'urgent'
          ? item.priority
          : null,
      canonical_code:
        typeof item.canonical_code === 'string' ? item.canonical_code : null,
      source: typeof item.source === 'string' ? item.source : null,
      performed_date:
        typeof item.performed_date === 'string' ? item.performed_date : null,
      reason: typeof item.reason === 'string' ? item.reason : null,
    }));
}

function readScores(value: unknown): DerivedScore[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter(
      (item): item is Record<string, unknown> =>
        typeof item === 'object' && item !== null,
    )
    .map((item) => ({
      code: typeof item.code === 'string' ? item.code : 'UNKNOWN',
      label: typeof item.label === 'string' ? item.label : 'Skor',
      status: typeof item.status === 'string' ? item.status : 'unavailable',
      value: typeof item.value === 'number' ? item.value : null,
      band: typeof item.band === 'string' ? item.band : null,
      band_label: typeof item.band_label === 'string' ? item.band_label : null,
      formula: typeof item.formula === 'string' ? item.formula : '—',
      inputs: Array.isArray(item.inputs)
        ? item.inputs
            .filter(
              (input): input is Record<string, unknown> =>
                typeof input === 'object' && input !== null,
            )
            .map((input) => ({
              name: typeof input.name === 'string' ? input.name : 'Değer',
              value:
                typeof input.value === 'number' || typeof input.value === 'string'
                  ? input.value
                  : null,
              raw_value:
                typeof input.raw_value === 'string' ? input.raw_value : null,
              unit: typeof input.unit === 'string' ? input.unit : null,
            }))
        : [],
      missing: readStringList(item.missing),
      flag: typeof item.flag === 'string' ? item.flag : null,
      note: typeof item.note === 'string' ? item.note : null,
    }));
}

function readConsistencyChecks(value: unknown): ConsistencyCheck[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter(
      (item): item is Record<string, unknown> =>
        typeof item === 'object' && item !== null,
    )
    .map((item) => ({
      code: typeof item.code === 'string' ? item.code : 'CHECK',
      severity: typeof item.severity === 'string' ? item.severity : 'info',
      kind: typeof item.kind === 'string' ? item.kind : 'info',
      label: typeof item.label === 'string' ? item.label : 'Çapraz kontrol',
      message: typeof item.message === 'string' ? item.message : '',
      values: Array.isArray(item.values)
        ? item.values
            .filter(
              (entry): entry is Record<string, unknown> =>
                typeof entry === 'object' && entry !== null,
            )
            .map((entry) => ({
              name: typeof entry.name === 'string' ? entry.name : 'Değer',
              value:
                typeof entry.value === 'number' || typeof entry.value === 'string'
                  ? entry.value
                  : null,
              raw_value:
                typeof entry.raw_value === 'string' ? entry.raw_value : null,
              unit: typeof entry.unit === 'string' ? entry.unit : null,
            }))
        : [],
    }));
}

function readRiskExplanation(value: unknown): RiskExplanation | null {
  if (typeof value !== 'object' || value === null) return null;
  const item = value as Record<string, unknown>;
  if (typeof item.score !== 'number') return null;

  const triggers = Array.isArray(item.triggers)
    ? item.triggers
        .filter(
          (trigger): trigger is Record<string, unknown> =>
            typeof trigger === 'object' && trigger !== null,
        )
        .map((trigger) => ({
          flag: typeof trigger.flag === 'string' ? trigger.flag : 'FLAG',
          label: typeof trigger.label === 'string' ? trigger.label : 'Dikkat sinyali',
          rule: typeof trigger.rule === 'string' ? trigger.rule : null,
          parameters: Array.isArray(trigger.parameters)
            ? trigger.parameters.filter(
                (parameter): parameter is NonNullable<RiskTrigger['parameters']>[number] =>
                  typeof parameter === 'object' && parameter !== null,
              )
            : [],
        }))
    : [];

  return {
    score: item.score,
    scale_min: typeof item.scale_min === 'number' ? item.scale_min : 1,
    scale_max: typeof item.scale_max === 'number' ? item.scale_max : 3,
    scale_label:
      typeof item.scale_label === 'string'
        ? item.scale_label
        : '1 düşük · 2 orta · 3 yüksek',
    basis: typeof item.basis === 'string' ? item.basis : 'Backend değerlendirme flagleri',
    triggers,
    note: typeof item.note === 'string' ? item.note : null,
  };
}

function readTemporalContext(value: unknown): TemporalContext | null {
  if (typeof value !== 'object' || value === null) return null;
  const item = value as Record<string, unknown>;
  return {
    laboratory_date:
      typeof item.laboratory_date === 'string' ? item.laboratory_date : null,
    ultrasound_date:
      typeof item.ultrasound_date === 'string' ? item.ultrasound_date : null,
    gap_days: typeof item.gap_days === 'number' ? item.gap_days : null,
    threshold_days:
      typeof item.threshold_days === 'number' ? item.threshold_days : null,
    warning: item.warning === true,
    message: typeof item.message === 'string' ? item.message : null,
  };
}

function priorityLabel(priority: ClaudeSuggestedTest['priority']) {
  if (priority === 'urgent') return 'Acil değerlendirme';
  if (priority === 'soon') return 'Yakın zamanda';
  if (priority === 'routine') return 'Rutin';
  return null;
}

function riskPresentation(value: unknown) {
  if (value === 3) {
    return {
      label: 'Yüksek risk · 3/3 ölçek',
      badgeClass: 'border-rose-200 bg-rose-50 text-rose-700',
      action:
        'Öncelikli hekim değerlendirmesi önerilir. Klinik durum kötüleşiyorsa gecikmeden yeniden değerlendirme yapılmalıdır.',
    };
  }

  if (value === 2) {
    return {
      label: 'Orta risk · 2/3 ölçek',
      badgeClass: 'border-amber-200 bg-amber-50 text-amber-700',
      action:
        'Bulguların klinik muayene ve mevcut tetkiklerle birlikte hekim tarafından değerlendirilmesi önerilir.',
    };
  }

  if (value === 1) {
    return {
      label: 'Düşük risk · 1/3 ölçek',
      badgeClass: 'border-emerald-200 bg-emerald-50 text-emerald-700',
      action:
        'Rutin hekim doğrulaması önerilir. Yeni veya kötüleşen bulgular gelişirse yeniden değerlendirme yapılmalıdır.',
    };
  }

  return null;
}

function flagLabel(flag: string) {
  if (flag === 'ULTRASOUND_CRITICAL_REVIEW') {
    return 'Ultrason: sonuç bölümünde kritik değerlendirme';
  }
  if (flag === 'ULTRASOUND_ABNORMAL_REVIEW') {
    return 'Ultrason: sonuç bölümünde dikkat gerektiren ifade';
  }
  if (flag === 'TEMPORAL_GAP_GT_90_DAYS') {
    return 'Kaynaklar arasında 90 günden uzun zaman farkı';
  }
  if (flag === 'SERUM_URINE_GLUCOSE_UNEXPECTED') {
    return 'Serum–idrar glukozu birlikte beklenmedik';
  }
  return flag.replace(/_/g, ' ').toLocaleLowerCase('tr-TR');
}

function labStatusPresentation(status: string) {
  if (status === 'high') {
    return {
      label: 'YÜKSEK',
      badge: 'border-rose-200 bg-rose-50 text-rose-700',
      card: 'border-rose-100',
    };
  }
  return {
    label: 'DÜŞÜK',
    badge: 'border-sky-200 bg-sky-50 text-sky-700',
    card: 'border-sky-100',
  };
}

function findingValue(finding: ExtendedFinding) {
  return finding.display_value ?? finding.raw_value ?? finding.value ?? '—';
}

function formatInput(input: ScoreInput) {
  const value = input.raw_value ?? input.value;
  if (value == null) return `${input.name}: —`;
  return `${input.name}: ${value}${input.unit ? ` ${input.unit}` : ''}`;
}

function SuggestedTestList({
  title,
  tests,
}: {
  title: string;
  tests: ClaudeSuggestedTest[];
}) {
  if (tests.length === 0) return null;

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <h4 className="text-sm font-semibold text-slate-950">{title}</h4>
      <ul className="mt-3 space-y-3">
        {tests.map((test, index) => {
          const priority = priorityLabel(test.priority);
          return (
            <li
              key={`${test.name}-${index}`}
              className="rounded-lg border border-slate-200 bg-white p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-semibold text-slate-900">
                  {test.name}
                </span>
                {priority ? (
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
                    {priority}
                  </span>
                ) : null}
              </div>
              {test.rationale ? (
                <p className="mt-2 text-xs leading-5 text-slate-600">
                  {test.rationale}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function DeterministicScores({ scores }: { scores: DerivedScore[] }) {
  if (scores.length === 0) return null;

  return (
    <section className="mt-4 rounded-xl border border-indigo-200 bg-indigo-50/40 p-4">
      <div>
        <h4 className="text-sm font-semibold text-indigo-950">
          Deterministik skorlar ve oranlar
        </h4>
        <p className="mt-1 text-xs leading-5 text-slate-600">
          Formül ve kullanılan değerler gösterilir; eksik parametre varsa tahmin yapılmaz.
        </p>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {scores.map((score) => (
          <div
            key={score.code}
            className="rounded-lg border border-indigo-100 bg-white p-3"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-slate-950">{score.label}</p>
                <p className="mt-1 text-xs text-slate-500">{score.formula}</p>
              </div>
              <span
                className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
                  score.status === 'calculated'
                    ? score.band === 'high'
                      ? 'border-rose-200 bg-rose-50 text-rose-700'
                      : score.band === 'low'
                        ? 'border-sky-200 bg-sky-50 text-sky-700'
                        : 'border-slate-200 bg-slate-50 text-slate-700'
                    : 'border-slate-200 bg-slate-50 text-slate-500'
                }`}
              >
                {score.status === 'calculated'
                  ? score.band_label ?? 'Hesaplandı'
                  : 'Hesaplanamadı'}
              </span>
            </div>

            {score.status === 'calculated' ? (
              <p className="mt-2 text-lg font-semibold text-slate-900">
                {score.value ?? '—'}
              </p>
            ) : (
              <p className="mt-2 text-xs font-medium text-slate-600">
                Eksik: {score.missing.join(', ') || 'gerekli veri'}
              </p>
            )}

            <div className="mt-2 flex flex-wrap gap-1.5">
              {score.inputs.map((input, index) => (
                <span
                  key={`${score.code}-${input.name}-${index}`}
                  className="rounded bg-slate-50 px-2 py-1 text-[11px] text-slate-600"
                >
                  {formatInput(input)}
                </span>
              ))}
            </div>

            {score.note ? (
              <p className="mt-2 text-[11px] leading-4 text-slate-500">{score.note}</p>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function CrossConsistency({ checks }: { checks: ConsistencyCheck[] }) {
  if (checks.length === 0) return null;

  return (
    <section className="mt-4 rounded-xl border border-amber-200 bg-amber-50/50 p-4">
      <h4 className="text-sm font-semibold text-amber-950">
        Çapraz tutarlılık kontrolleri
      </h4>
      <div className="mt-3 space-y-2">
        {checks.map((check) => (
          <div
            key={check.code}
            className={`rounded-lg border bg-white p-3 ${
              check.kind === 'unexpected' ? 'border-amber-200' : 'border-slate-200'
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-semibold text-slate-900">{check.label}</p>
              <span className="rounded-full bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
                {check.kind === 'unexpected' ? 'Doğrulama gerekli' : 'Bağlamsal ilişki'}
              </span>
            </div>
            <p className="mt-1 text-xs leading-5 text-slate-600">{check.message}</p>
            {check.values.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {check.values.map((value, index) => (
                  <span
                    key={`${check.code}-${value.name}-${index}`}
                    className="rounded bg-slate-50 px-2 py-1 text-[11px] text-slate-600"
                  >
                    {formatInput(value)}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function RiskDetails({
  explanation,
  flags,
}: {
  explanation: RiskExplanation | null;
  flags: string[];
}) {
  if (!explanation && flags.length === 0) return null;

  return (
    <details className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
      <summary className="cursor-pointer text-sm font-semibold text-slate-900">
        Risk skorunun nasıl oluştuğunu göster
      </summary>
      {explanation ? (
        <div className="mt-3 space-y-3">
          <p className="text-xs leading-5 text-slate-600">
            Ölçek: <span className="font-semibold">{explanation.scale_label}</span>.
            {' '}Kaynak: {explanation.basis}.
          </p>
          {explanation.triggers.length > 0 ? (
            <ul className="space-y-2">
              {explanation.triggers.map((trigger) => (
                <li
                  key={trigger.flag}
                  className="rounded-lg border border-slate-200 bg-white p-3"
                >
                  <p className="text-xs font-semibold text-slate-900">
                    {trigger.label}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Kural: {trigger.rule ?? 'backend review flag'} · {trigger.flag}
                  </p>
                  {trigger.parameters && trigger.parameters.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {trigger.parameters.map((parameter, index) => (
                        <span
                          key={`${trigger.flag}-${index}`}
                          className="rounded bg-slate-50 px-2 py-1 text-[11px] text-slate-600"
                        >
                          {parameter.name ?? 'Parametre'}: {parameter.value ?? '—'}
                          {parameter.unit ? ` ${parameter.unit}` : ''}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
          {explanation.note ? (
            <p className="text-[11px] leading-4 text-slate-500">{explanation.note}</p>
          ) : null}
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          {flags.map((flag) => (
            <span
              key={flag}
              className="rounded-full border border-amber-200 bg-white px-2.5 py-1 text-xs font-medium text-amber-800"
            >
              {flagLabel(flag)}
            </span>
          ))}
        </div>
      )}
    </details>
  );
}

export default function ClaudeEvaluationCard({
  hypothesis,
}: {
  hypothesis: ClaudeEvaluationHypothesis;
}) {
  const metadata = hypothesis.metadata_json ?? {};
  const possibleConditions = readStringList(metadata.possible_conditions);
  const laboratoryTests = readSuggestedTests(metadata.recommended_laboratory_tests);
  const imagingTests = readSuggestedTests(metadata.recommended_imaging_tests);
  const alreadyPerformed = readAlreadyPerformed(metadata.already_performed_tests);
  const limitations = readStringList(metadata.limitations);
  const flags = readStringList(metadata.flags);
  const pathologicalFindings = readPathologicalFindings(metadata.pathological_findings);
  const derivedScores = readScores(metadata.derived_scores);
  const consistencyChecks = readConsistencyChecks(metadata.cross_consistency_checks);
  const riskExplanation = readRiskExplanation(metadata.risk_explanation);
  const temporal = readTemporalContext(metadata.temporal_context);

  const labFindings = pathologicalFindings.filter(
    (finding) =>
      finding.source === 'laboratory' &&
      (finding.status === 'high' || finding.status === 'low'),
  );
  const explainedLabFindings = labFindings.filter(
    (finding) => Boolean(finding.clinical_interpretation),
  );
  const compactLabFindings = labFindings.filter(
    (finding) => !finding.clinical_interpretation,
  );
  const vitalFindings = pathologicalFindings.filter(
    (finding) => finding.source === 'vital',
  );
  const compactMode = metadata.compact_mode === true;
  const aiCalled = metadata.ai_called === true;
  const risk = riskPresentation(metadata.risk);
  const displayTitle = compactMode ? 'Klinik risk özeti' : hypothesis.title;
  const hasEndSection =
    possibleConditions.length > 0 ||
    laboratoryTests.length > 0 ||
    imagingTests.length > 0 ||
    alreadyPerformed.length > 0;

  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <span>AI destekli klinik değerlendirme</span>
            {compactMode ? (
              <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] normal-case tracking-normal text-slate-600">
                Klinik + laboratuvar + ultrason sonucu
              </span>
            ) : null}
          </div>
          <h3 className="mt-2 text-lg font-semibold text-slate-950">{displayTitle}</h3>
        </div>

        <div className="flex flex-wrap gap-2">
          {risk ? (
            <span
              className={`whitespace-nowrap rounded-full border px-3 py-1 text-xs font-semibold ${risk.badgeClass}`}
            >
              {risk.label}
            </span>
          ) : null}
          <span className="whitespace-nowrap rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-xs font-semibold text-violet-700">
            Hekim doğrulaması gerekli
          </span>
        </div>
      </div>

      {temporal?.warning ? (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">
          <span className="font-semibold">Zamansal uyarı:</span>{' '}
          {temporal.message ??
            `Kaynaklar arasında ${temporal.gap_days ?? 'belirgin'} gün fark var.`}
        </div>
      ) : null}

      <div
        className={`mt-5 grid gap-3 ${
          risk ? 'lg:grid-cols-[minmax(0,1.7fr)_minmax(260px,1fr)]' : ''
        }`}
      >
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Değerlendirme
          </p>
          <p className="mt-2 whitespace-normal break-words text-sm leading-6 text-slate-700">
            {hypothesis.summary}
          </p>
          <p className="mt-3 text-xs text-slate-500">
            {aiCalled
              ? 'AI destekli klinik sentez'
              : 'Kurallı klinik değerlendirme'}
          </p>
        </div>

        {risk ? (
          <div className="rounded-xl border border-blue-100 bg-blue-50/60 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
              Önerilen aksiyon
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-700">{risk.action}</p>
          </div>
        ) : null}
      </div>

      <RiskDetails explanation={riskExplanation} flags={flags} />
      <DeterministicScores scores={derivedScores} />
      <CrossConsistency checks={consistencyChecks} />

      {labFindings.length > 0 ? (
        <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h4 className="text-sm font-semibold text-slate-950">
                Yüksek / Düşük Laboratuvar Bulguları
              </h4>
              <p className="mt-1 text-xs text-slate-500">
                Referans dışı parametreler; kaynak tarihleri ve varsa trend deltalarıyla gösterilir.
              </p>
            </div>
            <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700">
              {labFindings.length} parametre
            </span>
          </div>

          {explainedLabFindings.length > 0 ? (
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              {explainedLabFindings.map((finding, index) => {
                const tone = labStatusPresentation(finding.status);
                return (
                  <div
                    key={`${finding.name}-${finding.status}-${index}`}
                    className={`rounded-xl border bg-white p-4 ${tone.card}`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-slate-950">
                          {finding.name}
                        </p>
                        <p className="mt-1 text-sm text-slate-700">
                          {findingValue(finding)} {finding.unit ?? ''}
                        </p>
                        {finding.measured_at ? (
                          <p className="mt-1 text-[11px] text-slate-500">
                            Tarih: {finding.measured_at}
                          </p>
                        ) : null}
                      </div>
                      <span
                        className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${tone.badge}`}
                      >
                        {tone.label}
                      </span>
                    </div>

                    {finding.previous_value != null ? (
                      <p className="mt-2 text-[11px] leading-4 text-slate-500">
                        Önceki: {finding.previous_value}
                        {finding.absolute_difference != null
                          ? ` · Δ ${finding.absolute_difference}`
                          : ''}
                        {finding.percentage_difference != null
                          ? ` · %Δ ${finding.percentage_difference.toFixed(1)}`
                          : ''}
                        {finding.time_difference_days != null
                          ? ` · ${finding.time_difference_days} gün`
                          : ''}
                      </p>
                    ) : null}

                    <div className="mt-3 rounded-lg border border-violet-100 bg-violet-50/50 px-3 py-3">
                      <p className="text-xs font-semibold text-violet-900">
                        Klinik olarak ne anlama gelebilir?
                      </p>
                      <p className="mt-1 text-xs leading-5 text-slate-700">
                        {finding.clinical_interpretation}
                      </p>
                      {finding.clinical_note ? (
                        <p className="mt-2 border-t border-violet-100 pt-2 text-[11px] leading-4 text-slate-500">
                          {finding.clinical_note}
                        </p>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : null}

          {compactLabFindings.length > 0 ? (
            <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
              <p className="text-xs font-semibold text-slate-800">
                Genel açıklama sözlüğünde henüz yer almayan referans dışı sonuçlar
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {compactLabFindings.map((finding, index) => {
                  const tone = labStatusPresentation(finding.status);
                  return (
                    <span
                      key={`${finding.name}-compact-${index}`}
                      className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${tone.badge}`}
                    >
                      {finding.name}: {findingValue(finding)} {finding.unit ?? ''} ·{' '}
                      {tone.label}
                    </span>
                  );
                })}
              </div>
            </div>
          ) : null}

          <p className="mt-3 text-xs leading-5 text-slate-500">
            Yüksek/düşük sınıflandırması rapor referansına göre yapılır. Klinik anlam
            tek başına tanı koydurmaz.
          </p>
        </div>
      ) : null}

      {vitalFindings.length > 0 ? (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/60 p-4">
          <h4 className="text-sm font-semibold text-amber-950">Vital dikkat sinyalleri</h4>
          <div className="mt-3 flex flex-wrap gap-2">
            {vitalFindings.map((finding, index) => (
              <span
                key={`${finding.name}-${index}`}
                className="rounded-full border border-amber-200 bg-white px-2.5 py-1 text-xs font-medium text-amber-800"
              >
                {finding.display}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {flags.length > 0 ? (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/60 p-4">
          <h4 className="text-sm font-semibold text-amber-950">Dikkat sinyalleri</h4>
          <div className="mt-3 flex flex-wrap gap-2">
            {flags.map((flag) => (
              <span
                key={flag}
                className="rounded-full border border-amber-200 bg-white px-2.5 py-1 text-xs font-medium text-amber-800"
              >
                {flagLabel(flag)}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {limitations.length > 0 ? (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <h4 className="text-sm font-semibold text-amber-950">
            Dikkat edilmesi gereken noktalar
          </h4>
          <ul className="mt-2 space-y-1 text-xs leading-5 text-amber-900">
            {limitations.map((limitation) => (
              <li key={limitation}>• {limitation}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {hasEndSection ? (
        <section className="mt-5 border-t border-slate-200 pt-5">
          <div className="mb-4">
            <h4 className="text-base font-semibold text-slate-950">
              Olası ilişkiler ve ileri tetkikler
            </h4>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              Bulgular tanı değildir; ileri tetkiklerin gerçekten gerekli olup olmadığına
              hekim klinik bağlama göre karar verir. Vaka girdisinde zaten bulunan
              tetkikler yeniden öneri listesine konmaz.
            </p>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            {possibleConditions.length > 0 ? (
              <div className="rounded-xl border border-violet-200 bg-violet-50/60 p-4">
                <h5 className="text-sm font-semibold text-violet-950">
                  İlişkili olabilecek hastalıklar / durumlar
                </h5>
                <ul className="mt-3 space-y-2 text-sm leading-5 text-slate-700">
                  {possibleConditions.map((condition) => (
                    <li key={condition}>• {condition}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            <SuggestedTestList
              title="İleri laboratuvar tetkikleri"
              tests={laboratoryTests}
            />
            <SuggestedTestList
              title="İleri görüntüleme tetkikleri"
              tests={imagingTests}
            />
          </div>

          {alreadyPerformed.length > 0 ? (
            <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
              <h5 className="text-sm font-semibold text-emerald-950">
                Zaten yapılmış / mevcut veriden hesaplanabilir
              </h5>
              <p className="mt-1 text-xs leading-5 text-emerald-900/80">
                Bunlar aktif öneri listesinden çıkarıldı; bağlam için burada tutuluyor.
              </p>
              <ul className="mt-3 grid gap-2 md:grid-cols-2">
                {alreadyPerformed.map((test, index) => (
                  <li
                    key={`${test.name}-performed-${index}`}
                    className="rounded-lg border border-emerald-200 bg-white p-3"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-slate-900">
                        {test.name}
                      </span>
                      {test.performed_date ? (
                        <span className="text-[11px] font-medium text-slate-500">
                          {test.performed_date}
                        </span>
                      ) : null}
                    </div>
                    {test.reason ? (
                      <p className="mt-1 text-xs leading-5 text-slate-600">{test.reason}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}

      <p className="mt-5 border-t border-slate-100 pt-4 text-xs leading-5 text-slate-500">
        Bu değerlendirme klinik karar desteği içindir. AI çıktısı tek başına tanı veya
        tedavi kararı olarak kullanılmamalı; orijinal raporlar ve klinik muayene ile
        birlikte hekim tarafından doğrulanmalıdır.
      </p>
    </article>
  );
}
