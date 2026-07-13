import { NavLink } from 'react-router-dom';

const mainItems = [
  { label: '🏠 Hasta Özeti', to: '/' },
  { label: '👤 Hasta Kaydı', to: '/patients/demo' },
  { label: '🧠 AI Klinik Değerlendirme', to: '/clinical-hypotheses' },
  { label: '📈 Trend Analizi', to: '/timeline' },
  { label: '📄 Hasta Arşivi', to: '/patient-history' },
];

const workflowGroups = [
  {
    label: '🩸 Laboratuvar Analizi',
    to: '/analysis/mock',
    children: [
      { label: 'PDF yoluyla ekleme', to: '/analysis/mock?entry=pdf' },
      { label: 'Manuel yolla ekleme', to: '/analysis/mock?entry=manual' },
    ],
  },
];

const roadmapItems = [
  {
    label: 'Radyoloji Raporları',
    to: '/radiology',
    phase: 'Faz 2',
  },
  {
    label: 'Medikal Görüntüleme',
    to: '/roadmap/imaging',
    phase: 'Faz 2.5',
  },
  {
    label: 'Patoloji',
    to: '/roadmap/pathology',
    phase: 'Faz 3',
  },
  {
    label: 'Kardiyoloji',
    to: '/roadmap/cardiology',
    phase: 'Faz 3.1',
  },
  {
    label: 'Mikrobiyoloji',
    to: '/roadmap/microbiology',
    phase: 'Faz 3.2',
  },
];

const getLinkClassName = ({ isActive }: { isActive: boolean }) =>
  [
    'block rounded-lg px-4 py-3 text-sm font-medium leading-5 transition',
    isActive
      ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-100'
      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950',
  ].join(' ');

const getChildLinkClassName = ({ isActive }: { isActive: boolean }) =>
  [
    'block rounded-md px-3 py-2 text-xs font-medium leading-5 transition',
    isActive
      ? 'bg-cyan-50 text-cyan-800'
      : 'text-slate-500 hover:bg-slate-50 hover:text-slate-800',
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
          {mainItems.slice(0, 2).map((item) => (
            <NavLink key={item.to} to={item.to} className={getLinkClassName}>
              {item.label}
            </NavLink>
          ))}

          {workflowGroups.map((group) => (
            <div key={group.to} className="rounded-lg border border-slate-100 bg-slate-50/60 p-1">
              <NavLink to={group.to} className={getLinkClassName}>
                {group.label}
              </NavLink>
              <div className="mt-1 space-y-1 border-l border-slate-200 pl-3">
                {group.children.map((child) => (
                  <NavLink key={child.to} to={child.to} className={getChildLinkClassName}>
                    {child.label}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}

          <div className="pt-3">
            <p className="px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">
              Geliştirme yol haritası
            </p>
            <div className="mt-2 space-y-1">
              {roadmapItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    [
                      'flex items-center justify-between gap-3 rounded-lg px-4 py-3 text-sm font-medium transition',
                      isActive
                        ? 'bg-amber-50 text-amber-900 ring-1 ring-amber-100'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950',
                    ].join(' ')
                  }
                >
                  <span>{item.label}</span>
                  <span className="rounded-full bg-amber-100 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-amber-800">
                    {item.phase}
                  </span>
                </NavLink>
              ))}
            </div>
          </div>

          {mainItems.slice(2).map((item) => (
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
          {[
            ...mainItems,
            ...workflowGroups.flatMap((group) => [
              { label: group.label, to: group.to },
              ...group.children,
            ]),
            ...roadmapItems,
          ].map((item) => (
            <NavLink
              key={`${item.to}-${item.label}`}
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
