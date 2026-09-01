import type {
  ClaudeEvaluationHypothesis,
  ClaudePathologicalFinding,
  ClaudeSuggestedTest,
} from '../../services/claudeReviewClient';

function readStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}

function readPathologicalFindings(value: unknown): ClaudePathologicalFinding[] {
  if (!Array.isArray(value)) return [];

  return value.filter((item): item is ClaudePathologicalFinding => {
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

function priorityLabel(priority: ClaudeSuggestedTest['priority']) {
  if (priority === 'urgent') return 'Acil değerlendirme';
  if (priority === 'soon') return 'Yakın zamanda';
  if (priority === 'routine') return 'Rutin';
  return null;
}

function riskPresentation(value: unknown) {
  if (value === 3) {
    return {
      label: 'Yüksek risk · 3/3',
      badgeClass: 'border-rose-200 bg-rose-50 text-rose-700',
      action:
        'Öncelikli hekim değerlendirmesi önerilir. Klinik durum kötüleşiyorsa gecikmeden yeniden değerlendirme yapılmalıdır.',
    };
  }

  if (value === 2) {
    return {
      label: 'Orta risk · 2/3',
      badgeClass: 'border-amber-200 bg-amber-50 text-amber-700',
      action:
        'Bulguların klinik muayene ve mevcut tetkiklerle birlikte hekim tarafından değerlendirilmesi önerilir.',
    };
  }

  if (value === 1) {
    return {
      label: 'Düşük risk · 1/3',
      badgeClass: 'border-emerald-200 bg-emerald-50 text-emerald-700',
      action:
        'Rutin hekim doğrulaması önerilir. Yeni veya kötüleşen bulgular gelişirse yeniden değerlendirme yapılmalıdır.',
    };
  }

  return null;
}

function flagLabel(flag: string) {
  if (flag === 'ULTRASOUND_CRITICAL_REVIEW') {
    return 'Ultrason: kritik bulgu incelemesi';
  }
  if (flag === 'ULTRASOUND_ABNORMAL_REVIEW') {
    return 'Ultrason: dikkat gerektiren bulgu';
  }
  return flag.replace(/_/g, ' ').toLocaleLowerCase('tr-TR');
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

export default function ClaudeEvaluationCard({
  hypothesis,
}: {
  hypothesis: ClaudeEvaluationHypothesis;
}) {
  const metadata = hypothesis.metadata_json ?? {};
  const possibleConditions = readStringList(metadata.possible_conditions);
  const laboratoryTests = readSuggestedTests(metadata.recommended_laboratory_tests);
  const imagingTests = readSuggestedTests(metadata.recommended_imaging_tests);
  const limitations = readStringList(metadata.limitations);
  const flags = readStringList(metadata.flags);
  const pathologicalFindings = readPathologicalFindings(metadata.pathological_findings);
  const compactMode = metadata.compact_mode === true;
  const aiCalled = metadata.ai_called === true;
  const risk = riskPresentation(metadata.risk);
  const displayTitle = compactMode ? 'Klinik risk özeti' : hypothesis.title;

  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <span>AI destekli klinik değerlendirme</span>
            {compactMode ? (
              <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] normal-case tracking-normal text-slate-600">
                Klinik + laboratuvar + ultrason
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

      <div className={`mt-5 grid gap-3 ${risk ? 'lg:grid-cols-[minmax(0,1.7fr)_minmax(260px,1fr)]' : ''}`}>
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Değerlendirme
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            {hypothesis.summary}
          </p>
          <p className="mt-3 text-xs text-slate-500">
            {aiCalled
              ? 'AI destekli kısa klinik yorum'
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

      {pathologicalFindings.length > 0 ? (
        <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50/60 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="text-sm font-semibold text-rose-950">Patolojik Bulgular</h4>
            <span className="rounded-full border border-rose-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-rose-700">
              {pathologicalFindings.length} bulgu
            </span>
          </div>
          <ul className="mt-3 space-y-2">
            {pathologicalFindings.map((finding, index) => (
              <li
                key={`${finding.source}-${finding.name}-${finding.status}-${index}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-rose-100 bg-white px-3 py-2"
              >
                <span className="text-sm font-medium text-slate-900">
                  {finding.display}
                </span>
                <span className="text-[11px] font-semibold uppercase tracking-wide text-rose-700">
                  {finding.source === 'laboratory' ? 'Laboratuvar' : 'Vital'}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs leading-5 text-rose-800">
            Bu alan yalnızca sistem tarafından yüksek/düşük olarak sınıflandırılan
            yapılandırılmış bulgulardan oluşturulur.
          </p>
        </div>
      ) : null}

      {pathologicalFindings.length === 0 && flags.length > 0 ? (
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

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {possibleConditions.length > 0 ? (
          <div className="rounded-xl border border-violet-200 bg-violet-50/60 p-4">
            <h4 className="text-sm font-semibold text-violet-950">
              Olası klinik durumlar
            </h4>
            <ul className="mt-3 space-y-2 text-sm leading-5 text-slate-700">
              {possibleConditions.map((condition) => (
                <li key={condition}>• {condition}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <SuggestedTestList
          title="Değerlendirilebilecek laboratuvar tetkikleri"
          tests={laboratoryTests}
        />
        <SuggestedTestList
          title="Değerlendirilebilecek görüntüleme tetkikleri"
          tests={imagingTests}
        />
      </div>

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

      <p className="mt-5 border-t border-slate-100 pt-4 text-xs leading-5 text-slate-500">
        Bu değerlendirme klinik karar desteği içindir. AI çıktısı tek başına tanı veya
        tedavi kararı olarak kullanılmamalı; orijinal raporlar ve klinik muayene ile
        birlikte hekim tarafından doğrulanmalıdır.
      </p>
    </article>
  );
}
