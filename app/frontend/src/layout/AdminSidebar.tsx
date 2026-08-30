import { Link, NavLink } from 'react-router-dom';

const adminItems = [
  { label: '📡 Canlı Trafik', to: '/admin/analytics' },
  { label: '🤖 AI Kullanımı', to: '/admin/ai-costs' },
  { label: '💬 Geri Bildirimler', to: '/admin/feedback' },
];

const linkClassName = ({ isActive }: { isActive: boolean }) =>
  [
    'flex items-center rounded-lg px-3 py-2.5 text-sm font-medium leading-5 transition',
    isActive
      ? 'bg-violet-50 text-violet-700 ring-1 ring-violet-100'
      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950',
  ].join(' ');

export default function AdminSidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-72 flex-col border-r border-slate-200 bg-white px-5 py-6 lg:flex">
      <div className="mb-6">
        <Link
          to="/admin/analytics"
          aria-label="MediCore AI yönetici paneli"
          className="inline-flex rounded-lg outline-none transition hover:opacity-80 focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-2"
        >
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-slate-950 text-lg font-bold text-white shadow-sm">
            M
          </div>
        </Link>
        <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-violet-700">
          Yönetici Paneli
        </p>
        <p className="mt-1 text-xs leading-5 text-slate-500">
          Sistem trafiği, AI kullanımı ve kullanıcı geri bildirimleri.
        </p>
      </div>

      <nav className="space-y-1">
        {adminItems.map((item) => (
          <NavLink key={item.to} to={item.to} className={linkClassName}>
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto rounded-xl border border-violet-100 bg-violet-50/60 p-3.5">
        <p className="text-xs font-bold uppercase tracking-wide text-violet-700">
          Ayrı yönetim alanı
        </p>
        <p className="mt-1.5 text-xs leading-5 text-slate-600">
          Hasta, laboratuvar ve klinik değerlendirme ekranları yönetici panelinde gösterilmez.
        </p>
      </div>
    </aside>
  );
}
