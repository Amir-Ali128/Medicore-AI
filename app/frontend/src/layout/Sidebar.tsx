import { NavLink } from 'react-router-dom';

import { getStoredUser } from '../services/authClient';

type NavItem = {
  label: string;
  to: string;
  adminOnly?: boolean;
};

const items: NavItem[] = [
  { label: '🏠 Ana Sayfa', to: '/' },
  { label: '📡 Canlı Trafik', to: '/admin/analytics', adminOnly: true },
  { label: '👤 Hasta Bilgileri', to: '/patients/demo' },
  { label: '✉️ Gönder', to: '/send' },
  { label: '🩸 Laboratuvar Sonuçları', to: '/analysis/mock' },
  { label: '🩻 Radyoloji ve Tetkik Raporları', to: '/radiology' },
  { label: '🧩 Bulguları Değerlendir', to: '/combined-evaluation' },
  { label: '📈 Trend Analizi', to: '/timeline' },
  { label: '📄 Arşiv', to: '/patient-history' },
];

const getLinkClassName = ({ isActive }: { isActive: boolean }) =>
  [
    'flex items-center rounded-lg px-3 py-2.5 text-sm font-medium leading-5 transition',
    isActive
      ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-100'
      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950',
  ].join(' ');

export default function Sidebar() {
  const user = getStoredUser();
  const visibleItems = items.filter((item) => !item.adminOnly || user?.role === 'admin');

  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-72 flex-col border-r border-slate-200 bg-white px-5 py-6 lg:flex">
      <div className="mb-5">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-blue-600 text-lg font-bold text-white shadow-sm">
          M
        </div>
        <p className="mt-4 text-xs font-semibold uppercase text-cyan-700">
          Klinik Karar Desteği
        </p>
        <p className="mt-1 text-xs leading-5 text-slate-500">
          İşleme başlamak için ilgili bölümü seçin.
        </p>
      </div>

      <nav className="space-y-1 overflow-y-auto pr-1">
        {visibleItems.map((item) => (
          <NavLink key={item.to} to={item.to} className={getLinkClassName}>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
