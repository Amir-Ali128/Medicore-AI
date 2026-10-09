import { NavLink } from 'react-router-dom';

import { getStoredUser } from '../services/authClient';

export default function MobileNavigation() {
  const user = getStoredUser();
  const items =
    user?.role === 'admin'
      ? [
          { label: 'Analitik', to: '/admin/analytics', icon: '◫' },
          { label: 'AI', to: '/admin/ai-costs', icon: '✦' },
          { label: 'Mesajlar', to: '/admin/feedback', icon: '◌' },
        ]
      : [
          { label: 'Ana', to: '/', icon: '⌂' },
          { label: 'Yeni Vaka', to: '/case?new=1', icon: '+' },
          { label: 'Geçmiş Vakalar', to: '/history', icon: '↺' },
        ];

  return (
    <nav className="fixed inset-x-3 bottom-3 z-30 rounded-[24px] border border-slate-200 bg-white/95 p-2 shadow-2xl backdrop-blur lg:hidden">
      <div className="grid grid-cols-3 gap-1">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              [
                'flex flex-col items-center justify-center rounded-2xl px-2 py-2.5 text-[11px] font-semibold transition',
                isActive ? 'bg-slate-950 text-white' : 'text-slate-500',
              ].join(' ')
            }
          >
            <span className="text-lg leading-none">{item.icon}</span>
            <span className="mt-1">{item.label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
