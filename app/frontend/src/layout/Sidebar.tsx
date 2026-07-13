import { NavLink } from 'react-router-dom';

type NavItem = {
  label: string;
  to: string;
  status?: string;
  tone?: 'active' | 'beta' | 'pilot' | 'preview' | 'research';
};

const topItems: NavItem[] = [
  { label: '🏠 Ana Sayfa', to: '/' },
  { label: '👤 Hasta Özeti', to: '/patients/demo' },
];

const coreItems: NavItem[] = [
  { label: '🩸 Laboratuvar Analizi', to: '/analysis/mock', status: 'Aktif', tone: 'active' },
  { label: '🩻 Radyoloji Rapor Analizi', to: '/radiology', status: 'Test', tone: 'beta' },
  { label: '🧠 Yapay Zekâ Klinik Değerlendirme', to: '/clinical-hypotheses', status: 'Aktif', tone: 'active' },
  { label: '📈 Trend Analizi', to: '/timeline', status: 'Test', tone: 'beta' },
  { label: '📄 Raporlar ve Arşiv', to: '/patient-history', status: 'Aktif', tone: 'active' },
];

const clinicalItems: NavItem[] = [
  { label: '🩺 İç Hastalıkları', to: '/clinics/internal-medicine', status: 'Pilot', tone: 'pilot' },
  { label: '🫀 Kardiyoloji', to: '/roadmap/cardiology', status: 'Ön izleme', tone: 'preview' },
  { label: '🫁 Göğüs Hastalıkları', to: '/clinics/pulmonology', status: 'Ön izleme', tone: 'preview' },
];

const researchItems: NavItem[] = [
  { label: '🔬 Patoloji', to: '/roadmap/pathology', status: 'Araştırma', tone: 'research' },
  { label: '🧫 Mikrobiyoloji', to: '/roadmap/microbiology', status: 'Araştırma', tone: 'research' },
  { label: '🖼️ Medikal Görüntüleme', to: '/roadmap/imaging', status: 'Araştırma', tone: 'research' },
];

const statusClasses: Record<NonNullable<NavItem['tone']>, string> = {
  active: 'bg-emerald-100 text-emerald-800',
  beta: 'bg-sky-100 text-sky-800',
  pilot: 'bg-violet-100 text-violet-800',
  preview: 'bg-amber-100 text-amber-800',
  research: 'bg-slate-200 text-slate-700',
};

const getLinkClassName = ({ isActive }: { isActive: boolean }) =>
  [
    'flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-sm font-medium leading-5 transition',
    isActive
      ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-100'
      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950',
  ].join(' ');

function NavigationItem({ item }: { item: NavItem }) {
  return (
    <NavLink to={item.to} className={getLinkClassName}>
      <span className="min-w-0 truncate">{item.label}</span>
      {item.status && item.tone ? (
        <span
          className={`shrink-0 rounded-full px-2 py-1 text-[9px] font-bold uppercase tracking-wide ${statusClasses[item.tone]}`}
        >
          {item.status}
        </span>
      ) : null}
    </NavLink>
  );
}

function NavigationSection({ title, items }: { title: string; items: NavItem[] }) {
  return (
    <section className="pt-3">
      <p className="px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">
        {title}
      </p>
      <div className="mt-2 space-y-1">
        {items.map((item) => (
          <NavigationItem key={item.to} item={item} />
        ))}
      </div>
    </section>
  );
}

const mobileItems = [...topItems, ...coreItems, ...clinicalItems, ...researchItems];

export default function Sidebar() {
  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-72 flex-col border-r border-slate-200 bg-white px-5 py-6 lg:flex">
        <div className="mb-5">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-blue-600 text-lg font-bold text-white shadow-sm">
            M
          </div>
          <p className="mt-4 text-xs font-semibold uppercase text-cyan-700">
            Klinik Karar Desteği
          </p>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            Çalışan temel özellikler, kontrollü klinik pilotlar ve araştırma modülleri.
          </p>
        </div>

        <nav className="space-y-1 overflow-y-auto pr-1">
          <div className="space-y-1">
            {topItems.map((item) => (
              <NavigationItem key={item.to} item={item} />
            ))}
          </div>

          <NavigationSection title="Temel modüller" items={coreItems} />
          <NavigationSection title="Klinik branşlar" items={clinicalItems} />
          <NavigationSection title="Araştırma modülleri" items={researchItems} />
        </nav>

        <div className="mt-4 rounded-lg border border-blue-100 bg-blue-50 p-4">
          <p className="text-xs leading-5 text-blue-900">
            Rozetler modüllerin geliştirme durumunu gösterir. Araştırma ve ön izleme alanları klinik kullanım için aktif değildir.
          </p>
        </div>
      </aside>

      <div className="border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
        <nav className="flex gap-2 overflow-x-auto">
          {mobileItems.map((item) => (
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
