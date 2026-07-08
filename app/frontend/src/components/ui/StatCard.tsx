type StatCardProps = {
  title: string;
  value: string;
  helper: string;
  accent?: 'blue' | 'cyan' | 'slate';
};

const accentClasses: Record<NonNullable<StatCardProps['accent']>, string> = {
  blue: 'bg-blue-600',
  cyan: 'bg-cyan-600',
  slate: 'bg-slate-700',
};

export default function StatCard({
  title,
  value,
  helper,
  accent = 'blue',
}: StatCardProps) {
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-slate-500">{title}</p>
          <p className="mt-3 text-3xl font-semibold text-slate-950">
            {value}
          </p>
        </div>
        <span className={`mt-1 h-3 w-3 rounded-full ${accentClasses[accent]}`} />
      </div>
      <p className="mt-4 text-sm leading-6 text-slate-500">{helper}</p>
    </article>
  );
}
