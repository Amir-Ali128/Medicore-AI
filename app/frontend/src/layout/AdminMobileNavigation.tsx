import { NavLink } from 'react-router-dom';

const adminItems = [
  { label: 'Trafik', icon: '📡', to: '/admin/analytics' },
  { label: 'AI', icon: '🤖', to: '/admin/ai-costs' },
  { label: 'Mesajlar', icon: '💬', to: '/admin/feedback' },
];

export default function AdminMobileNavigation() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 px-3 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 shadow-[0_-8px_30px_rgba(15,23,42,0.08)] backdrop-blur lg:hidden">
      <div className="mx-auto grid max-w-md grid-cols-3 gap-2">
        {adminItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              [
                'flex min-w-0 flex-col items-center justify-center rounded-2xl px-2 py-2 text-[11px] font-semibold transition',
                isActive
                  ? 'bg-violet-50 text-violet-700'
                  : 'text-slate-500 active:bg-slate-100',
              ].join(' ')
            }
          >
            <span className="text-lg leading-none" aria-hidden="true">{item.icon}</span>
            <span className="mt-1">{item.label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
