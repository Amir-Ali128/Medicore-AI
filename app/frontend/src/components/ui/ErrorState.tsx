type ErrorStateProps = {
  title?: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
};

export default function ErrorState({
  title = 'Unable to load workspace',
  description = 'Mock data could not be displayed.',
  actionLabel,
  onAction,
}: ErrorStateProps) {
  return (
    <div className="rounded-lg border border-rose-100 bg-white p-6 shadow-soft">
      <div className="rounded-lg border border-rose-100 bg-rose-50 p-4">
        <p className="text-xs font-semibold uppercase text-rose-700">
          Review workspace
        </p>
        <h2 className="mt-2 text-lg font-semibold text-slate-950">{title}</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          {description}
        </p>
      </div>
      {actionLabel && onAction ? (
        <button
          type="button"
          onClick={onAction}
          className="mt-4 rounded-lg border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-rose-700 transition hover:bg-rose-50"
        >
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
