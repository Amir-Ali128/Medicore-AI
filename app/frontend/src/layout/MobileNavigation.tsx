import { NavLink } from 'react-router-dom';

export default function MobileNavigation() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 px-4 pb-[max(0.65rem,env(safe-area-inset-bottom))] pt-2 shadow-[0_-8px_30px_rgba(15,23,42,0.08)] backdrop-blur lg:hidden">
      <div className="mx-auto max-w-md">
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            [
              'flex items-center justify-center gap-2 rounded-2xl px-4 py-3 text-sm font-semibold transition',
              isActive ? 'bg-slate-950 text-white' : 'bg-slate-100 text-slate-700',
            ].join(' ')
          }
        >
          <span aria-hidden="true">⌁</span>
          Vaka çalışma alanı
        </NavLink>
      </div>
    </nav>
  );
}
