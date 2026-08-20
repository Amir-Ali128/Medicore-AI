import { useEffect, useMemo, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';

import { getStoredUser } from '../services/authClient';

type NavItem = {
  label: string;
  shortLabel: string;
  icon: string;
  to: string;
  adminOnly?: boolean;
  patientOnly?: boolean;
};

const items: NavItem[] = [
  { label: 'Ana Sayfa', shortLabel: 'Ana', icon: '🏠', to: '/' },
  { label: 'Canlı Trafik', shortLabel: 'Trafik', icon: '📡', to: '/admin/analytics', adminOnly: true },
  { label: 'Geri Bildirimler', shortLabel: 'Mesajlar', icon: '💬', to: '/admin/feedback', adminOnly: true },
  { label: 'Hasta Bilgileri', shortLabel: 'Hasta', icon: '👤', to: '/patients/demo' },
  { label: 'Laboratuvar Sonuçları', shortLabel: 'Sonuç', icon: '🩸', to: '/analysis/mock' },
  { label: 'Radyoloji ve Diğer Tetkik Raporları', shortLabel: 'Tetkikler', icon: '🩻', to: '/radiology' },
  { label: 'Bulguları Değerlendir', shortLabel: 'Değerlendir', icon: '🧩', to: '/combined-evaluation' },
  { label: 'Trend Analizi', shortLabel: 'Trend', icon: '📈', to: '/timeline' },
  { label: 'Arşiv', shortLabel: 'Arşiv', icon: '📄', to: '/patient-history' },
  { label: 'Gönder', shortLabel: 'Gönder', icon: '✉️', to: '/send' },
  { label: 'Önerileriniz', shortLabel: 'Öneriler', icon: '💡', to: '/feedback', patientOnly: true },
];

function mobilePrimaryItems(role: string | undefined, visibleItems: NavItem[]) {
  const preferred = role === 'admin'
    ? ['/', '/admin/analytics', '/admin/feedback', '/patient-history']
    : role === 'patient'
      ? ['/', '/patients/demo', '/analysis/mock', '/patient-history']
      : ['/', '/patients/demo', '/send', '/analysis/mock'];

  const selected = preferred
    .map((path) => visibleItems.find((item) => item.to === path))
    .filter((item): item is NavItem => Boolean(item));

  return selected.slice(0, 4);
}

export default function MobileNavigation() {
  const user = getStoredUser();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  const visibleItems = useMemo(
    () => items.filter((item) => {
      if (item.adminOnly && user?.role !== 'admin') return false;
      if (item.patientOnly && user?.role !== 'patient') return false;
      return true;
    }),
    [user?.role],
  );
  const primaryItems = useMemo(
    () => mobilePrimaryItems(user?.role, visibleItems),
    [user?.role, visibleItems],
  );

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  return (
    <>
      {menuOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Menüyü kapat"
            onClick={() => setMenuOpen(false)}
            className="absolute inset-0 bg-slate-950/35 backdrop-blur-[1px]"
          />
          <div className="absolute inset-x-3 bottom-24 max-h-[70vh] overflow-y-auto rounded-3xl border border-slate-200 bg-white p-3 shadow-2xl">
            <div className="flex items-center justify-between px-2 pb-2 pt-1">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-cyan-700">MediCore AI</p>
                <p className="mt-1 text-sm font-semibold text-slate-950">Tüm bölümler</p>
              </div>
              <button
                type="button"
                onClick={() => setMenuOpen(false)}
                className="rounded-full bg-slate-100 px-3 py-2 text-sm font-semibold text-slate-700"
              >
                Kapat
              </button>
            </div>

            <nav className="grid grid-cols-2 gap-2">
              {visibleItems.map((item) => (
                <NavLink
                  key={`mobile-sheet-${item.to}`}
                  to={item.to}
                  className={({ isActive }) =>
                    [
                      'rounded-2xl border px-3 py-3 text-sm font-medium transition',
                      isActive
                        ? 'border-blue-200 bg-blue-50 text-blue-800'
                        : 'border-slate-200 bg-white text-slate-700 active:bg-slate-50',
                    ].join(' ')
                  }
                >
                  <span className="mr-2" aria-hidden="true">{item.icon}</span>
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        </div>
      ) : null}

      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 shadow-[0_-8px_30px_rgba(15,23,42,0.08)] backdrop-blur lg:hidden">
        <div className="mx-auto grid max-w-xl grid-cols-5 gap-1">
          {primaryItems.map((item) => (
            <NavLink
              key={`mobile-primary-${item.to}`}
              to={item.to}
              className={({ isActive }) =>
                [
                  'flex min-w-0 flex-col items-center justify-center rounded-2xl px-1 py-2 text-[11px] font-semibold transition',
                  isActive ? 'bg-blue-50 text-blue-700' : 'text-slate-500 active:bg-slate-100',
                ].join(' ')
              }
            >
              <span className="text-lg leading-none" aria-hidden="true">{item.icon}</span>
              <span className="mt-1 max-w-full truncate">{item.shortLabel}</span>
            </NavLink>
          ))}

          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            className="flex min-w-0 flex-col items-center justify-center rounded-2xl px-1 py-2 text-[11px] font-semibold text-slate-500 active:bg-slate-100"
          >
            <span className="text-lg leading-none" aria-hidden="true">☰</span>
            <span className="mt-1">Menü</span>
          </button>
        </div>
      </nav>
    </>
  );
}
