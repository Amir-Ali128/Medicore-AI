import { NavLink } from 'react-router-dom';

const navigationItems = [
  { label: 'Hasta Özeti', to: '/' },
  { label: 'Hasta Kaydı', to: '/patients/demo' },
  { label: 'Laboratuvar', to: '/analysis/mock' },
  { label: 'Radyoloji', to: '/radiology' },
  { label: 'Klinik Değerlendirme', to: '/clinical-hypotheses' },
  { label: 'Hasta Arşivi', to: '/patient-history' },
];

const getLinkClassName = ({ isActive }: { isActive: boolean }) =>
  [
    'block rounded-lg px-4 py-3 text-sm font-medium leading-5 transition',
    isActive
      ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-100'
      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950',
  ].join(' ');

export default function Sidebar() {
  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-72 flex-col border-r border-slate-200 bg-white px-5 py-6 lg:flex">
        <div className="mb-8">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-blue-600 text-lg font-bold text-white shadow-sm">
            M
          </div>
          <p className="mt-4 text-xs font-semibold uppercase text-cyan-700">
            Klinik Karar Desteği
          </p>
        </div>

        <nav className="space-y-2 overflow-y-auto pr-1">
          {navigationItems.map((item) => (
            <NavLink key={item.to} to={item.to} className={getLinkClassName}>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto rounded-lg border border-blue-100 bg-blue-50 p-4">
          <p className="text-sm leading-6 text-blue-900">
            Yeni hastaya geçmeden önce <strong>Hastayı kaydet ve temizle</strong>{' '}
            düğmesini kullanın.
          </p>
        </div>
      </aside>

      <div className="border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
        <nav className="flex gap-2 overflow-x-auto">
          {navigationItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                [
                  'shrink-0 rounded-lg px-3 py-2 text-sm font-medium leading-5',
                  isActive
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-slate-600 hover:bg-slate-100',
                ].join(' ')
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </>
  );
}
