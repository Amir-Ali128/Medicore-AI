import type {
  ClaudeEvaluationHypothesis,
  ClaudeSuggestedTest,
} from '../../services/claudeReviewClient';

function readStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
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

function SuggestedTestList({
  title,
  tests,
}: {
  title: string;
  tests: ClaudeSuggestedTest[];
}) {
  if (tests.length === 0) return null;

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
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
  const possibleConditions = readStringList(
    hypothesis.metadata_json?.possible_conditions,
  );
  const laboratoryTests = readSuggestedTests(
    hypothesis.metadata_json?.recommended_laboratory_tests,
  );
  const imagingTests = readSuggestedTests(
    hypothesis.metadata_json?.recommended_imaging_tests,
  );
  const limitations = readStringList(hypothesis.metadata_json?.limitations);

  return (
    <article className="rounded-xl border border-violet-200 bg-white p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="font-semibold text-slate-950">{hypothesis.title}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {hypothesis.summary}
          </p>
        </div>
        <span className="whitespace-nowrap rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-semibold text-violet-700">
          HEKİM KONTROLÜ GEREKİR
        </span>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        {possibleConditions.length > 0 ? (
          <div className="rounded-lg border border-violet-200 bg-violet-50/60 p-4">
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
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4">
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

      <p className="mt-4 text-xs leading-5 text-slate-500">
        Bu değerlendirme tanı veya tedavi kararı değildir. Klinik bilgiler,
        laboratuvar sonuçları ve görüntüleme raporlarıyla birlikte hekim tarafından
        doğrulanmalıdır.
      </p>
    </article>
  );
}
