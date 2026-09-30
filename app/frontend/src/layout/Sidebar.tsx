import { Link, NavLink } from 'react-router-dom';

export default function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-slate-200 bg-white px-5 py-6 lg:flex">
      <Link to="/" className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-950 text-sm font-bold text-white">
          M
        </div>
        <div>
          <p className="font-semibold tracking-tight text-slate-950">MediCore</p>
          <p className="text-xs text-slate-500">Clinical Workspace</p>
        </div>
      </Link>

      <nav className="mt-8">
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            [
              'flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition',
              isActive
                ? 'bg-slate-950 text-white'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950',
            ].join(' ')
          }
        >
          <span aria-hidden="true">⌁</span>
          Vaka çalışma alanı
        </NavLink>
      </nav>

      <div className="mt-auto rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">MediCore v1</p>
        <p className="mt-2 text-sm font-medium text-slate-800">Clinical + Lab + Reports</p>
        <p className="mt-2 text-xs leading-5 text-slate-500">
          Tek ekran, tek vaka, kaynak referanslarına sadık akış.
        </p>
      </div>
    </aside>
  );
}
