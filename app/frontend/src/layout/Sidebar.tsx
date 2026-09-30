import { NavLink } from 'react-router-dom';

import { getStoredUser } from '../services/authClient';

const clinicalItems = [
  { label: 'Ana Sayfa', to: '/', icon: '⌂' },
  { label: 'Yeni Vaka', to: '/case', icon: '+' },
  { label: 'Geçmiş', to: '/history', icon: '↺' },
];

const adminItems = [
  { label: 'Analitik', to: '/admin/analytics', icon: '◫' },
  { label: 'AI Kullanımı', to: '/admin/ai-costs', icon: '✦' },
  { label: 'Geri Bildirim', to: '/admin/feedback', icon: '◌' },
];

export default function Sidebar() {
  const user = getStoredUser();
  const items = user?.role === 'admin' ? adminItems : clinicalItems;

  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-slate-200/80 bg-white lg:flex lg:flex-col">
      <div className="px-6 py-7">
        <NavLink to="/" className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-2xl bg-slate-950 text-sm font-bold text-white">
            M
          </div>
          <div>
            <p className="text-base font-semibold tracking-tight text-slate-950">MediCore</p>
            <p className="text-xs text-slate-400">Clinical workspace</p>
          </div>
        </NavLink>
      </div>

      <nav className="px-3">
        <p className="px-3 pb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">
          {user?.role === 'admin' ? 'Yönetim' : 'Çalışma Alanı'}
        </p>
        <div className="space-y-1">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                [
                  'flex items-center gap-3 rounded-2xl px-3 py-3 text-sm font-medium transition',
                  isActive
                    ? 'bg-slate-950 text-white shadow-sm'
                    : 'text-slate-500 hover:bg-slate-100 hover:text-slate-950',
                ].join(' ')
              }
            >
              <span className="grid h-7 w-7 place-items-center rounded-xl bg-current/5 text-base" aria-hidden="true">
                {item.icon}
              </span>
              {item.label}
            </NavLink>
          ))}
        </div>
      </nav>

      {user?.role !== 'admin' ? (
        <div className="mt-auto p-4">
          <div className="rounded-3xl bg-blue-50 p-4">
            <p className="text-xs font-semibold text-blue-900">Basit akış</p>
            <p className="mt-1 text-xs leading-5 text-blue-700">
              Klinik + laboratuvar + raporlar. Hepsi tek vakada.
            </p>
          </div>
        </div>
      ) : null}
    </aside>
  );
}
