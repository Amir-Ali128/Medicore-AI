import { Link } from 'react-router-dom';

type EmptyStateProps = {
  title?: string;
  description?: string;
  actionLabel?: string;
  to?: string;
};

export default function EmptyState({
  title = 'No mock data available',
  description = 'There is no static review data to display.',
  actionLabel,
  to,
}: EmptyStateProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6 text-center shadow-soft">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-lg border border-cyan-100 bg-cyan-50">
        <div className="h-3 w-3 rounded-full bg-cyan-600" />
      </div>
      <h2 className="mt-4 text-lg font-semibold text-slate-950">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-500">
        {description}
      </p>
      {actionLabel && to ? (
        <Link
          to={to}
          className="mt-5 inline-flex rounded-lg border border-cyan-200 bg-cyan-50 px-4 py-2 text-sm font-medium text-cyan-800 transition hover:bg-cyan-100"
        >
          {actionLabel}
        </Link>
      ) : null}
    </div>
  );
}
