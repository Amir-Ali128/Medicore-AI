type LoadingStateProps = {
  title?: string;
  description?: string;
};

export default function LoadingState({
  title = 'Loading workspace',
  description = 'Preparing mock review data.',
}: LoadingStateProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-soft">
      <div className="animate-pulse space-y-4">
        <div className="h-3 w-24 rounded bg-cyan-100" />
        <div className="h-6 w-64 max-w-full rounded bg-slate-200" />
        <div className="h-4 w-full max-w-xl rounded bg-slate-100" />
      </div>
      <div className="mt-6">
        <h2 className="text-lg font-semibold text-slate-950">{title}</h2>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          {description}
        </p>
      </div>
    </div>
  );
}
