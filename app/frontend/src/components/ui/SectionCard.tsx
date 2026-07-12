import type { ReactNode } from 'react';

import UnifiedClinicalEvaluationPanel from '../clinical/UnifiedClinicalEvaluationPanel';

type SectionCardProps = {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
};

export default function SectionCard({
  title,
  description,
  action,
  children,
}: SectionCardProps) {
  const isLabPage =
    typeof window !== 'undefined' &&
    (window.location.hash.includes('/analysis/mock') ||
      window.location.pathname.includes('/analysis/mock'));

  if (isLabPage && title === 'Klinik kayıt') {
    return null;
  }

  const showUnifiedEvaluation = title === 'Klinik kayıt' && !isLabPage;

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-soft">
      <div className="flex flex-col gap-4 border-b border-slate-200 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-950">{title}</h2>
          {description ? (
            <p className="mt-1 text-sm leading-6 text-slate-500">{description}</p>
          ) : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      <div className="p-5">
        {children}
        {showUnifiedEvaluation ? <UnifiedClinicalEvaluationPanel /> : null}
      </div>
    </section>
  );
}
