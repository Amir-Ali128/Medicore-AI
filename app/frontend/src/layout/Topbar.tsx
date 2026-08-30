import { Link, useNavigate } from 'react-router-dom';

import { getStoredUser, logout } from '../services/authClient';

function roleLabel(role: string | undefined) {
  switch (role) {
    case 'doctor':
      return 'Doktor';
    case 'lab_staff':
      return 'Laboratuvar';
    case 'patient':
      return 'Bireysel kullanıcı';
    case 'admin':
      return 'Yönetici';
    default:
      return 'MediCore kullanıcı';
  }
}

export default function Topbar() {
  const navigate = useNavigate();
  const user = getStoredUser();
  const isAdmin = user?.role === 'admin';
  const homePath = isAdmin ? '/admin/analytics' : '/';

  function handleLogout() {
    logout();
    navigate(isAdmin ? '/admin/login' : '/login', { replace: true });
  }

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 px-3 py-3 backdrop-blur sm:px-6 sm:py-4 lg:px-8">
      <div className="flex items-center justify-between gap-3 lg:items-center">
        <div className="min-w-0">
          <Link
            to={homePath}
            aria-label={isAdmin ? 'MediCore AI yönetici ana sayfa' : 'MediCore AI ana sayfa'}
            className="flex min-w-0 items-center gap-2 rounded-xl outline-none transition hover:opacity-80 focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-sm font-bold text-white lg:hidden">
              M
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-base font-semibold text-slate-950 sm:text-xl">MediCore AI</h1>
              <p className="hidden text-sm text-slate-500 sm:block">
                {isAdmin ? 'Yönetici paneli' : 'Klinik değerlendirme sistemi'}
              </p>
            </div>
          </Link>
        </div>

        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-2.5 py-2 sm:px-4 sm:py-3">
            <div className="max-w-[120px] text-right sm:max-w-none">
              <p className="truncate text-xs font-semibold text-slate-900 sm:text-sm">
                @{user?.nickname ?? 'kullanici'}
              </p>
              <p className="text-[10px] text-slate-500 sm:text-xs">
                {roleLabel(user?.role)}
              </p>
            </div>

            <button
              type="button"
              onClick={handleLogout}
              className="rounded-lg bg-slate-950 px-2.5 py-2 text-[11px] font-semibold text-white transition hover:bg-slate-800 sm:px-3 sm:text-xs"
            >
              Çıkış
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
