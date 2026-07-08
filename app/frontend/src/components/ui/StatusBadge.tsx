type StatusBadgeStatus =
  | 'NORMAL'
  | 'LOW'
  | 'HIGH'
  | 'PENDING'
  | 'COMPLETED'
  | 'CREATED'
  | 'APPROVED'
  | 'EDITED'
  | 'REJECTED'
  | 'EXTRA_TEST_REQUESTED'
  | 'SPECIALIST_REFERRED'
  | 'OPEN'
  | 'IN_REVIEW'
  | 'BLOCKED';

type StatusBadgeProps = {
  status: StatusBadgeStatus;
};

const statusStyles: Record<StatusBadgeStatus, string> = {
  NORMAL: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  LOW: 'border-amber-200 bg-amber-50 text-amber-700',
  HIGH: 'border-rose-200 bg-rose-50 text-rose-700',
  PENDING: 'border-blue-200 bg-blue-50 text-blue-700',
  COMPLETED: 'border-cyan-200 bg-cyan-50 text-cyan-700',
  CREATED: 'border-slate-200 bg-slate-50 text-slate-700',
  APPROVED: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  EDITED: 'border-cyan-200 bg-cyan-50 text-cyan-700',
  REJECTED: 'border-rose-200 bg-rose-50 text-rose-700',
  EXTRA_TEST_REQUESTED: 'border-amber-200 bg-amber-50 text-amber-700',
  SPECIALIST_REFERRED: 'border-blue-200 bg-blue-50 text-blue-700',
  OPEN: 'border-blue-200 bg-blue-50 text-blue-700',
  IN_REVIEW: 'border-cyan-200 bg-cyan-50 text-cyan-700',
  BLOCKED: 'border-amber-200 bg-amber-50 text-amber-700',
};

export default function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-lg border px-2.5 py-1 text-xs font-semibold ${statusStyles[status]}`}
    >
      {status}
    </span>
  );
}
