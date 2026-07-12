import { useNavigate } from 'react-router-dom';

import { getStoredUser, logout } from '../services/authClient';
import {
  hasActivePatientSession,
  startNewPatientSession,
} from '../services/patientSessionStore';

export default function Topbar() {
  const navigate = useNavigate();
  const user = getStoredUser();

  function handleLogout() {
    logout();
    navigate('/login', { replace: true });
  }

  function handleNewPatient() {
    const hasActiveSession = hasActivePatientSession();
    const confirmed = window.confirm(
      hasActiveSession
        ? 'Mevcut hasta geçmişe kaydedilip tüm çalışma alanları yeni hasta için temizlensin mi?'
        : 'Yeni ve boş bir hasta çalışma alanı açılsın mı?',
    );
    if (!confirmed) return;

    startNewPatientSession();
    navigate('/analysis/mock', { replace: true });
    window.location.reload();
  }

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 px-4 py-4 backdrop-blur sm:px-6 lg:px-8">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-950">MediCore AI</h1>
          <p className="mt-1 text-sm text-slate-500">
            Hekim denetimli klinik karar destek sistemi
          </p>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-medium text-blue-800">
            Klinik çıktılar hekim değerlendirmesi için yapılandırılmıştır ve tanı değildir.
          </div>

          <button
            type="button"
            onClick={handleNewPatient}
            className="rounded-lg border border-blue-200 bg-white px-4 py-3 text-sm font-semibold text-blue-700 transition hover:bg-blue-50"
          >
            + Yeni hasta
          </button>

          <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3">
            <div className="text-right">
              <p className="text-sm font-semibold text-slate-900">
                {user?.full_name ?? 'Demo Hekim'}
              </p>
              <p className="text-xs text-slate-500">
                {user?.email ?? 'doctor@medicore.ai'}
              </p>
            </div>

            <button
              type="button"
              onClick={handleLogout}
              className="rounded-lg bg-slate-950 px-3 py-2 text-xs font-semibold text-white transition hover:bg-slate-800"
            >
              Çıkış
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
