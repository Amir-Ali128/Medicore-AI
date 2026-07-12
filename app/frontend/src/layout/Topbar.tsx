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

  function handleResetPatient() {
    const hasActiveSession = hasActivePatientSession();
    const confirmed = window.confirm(
      hasActiveSession
        ? 'Bu hastanın mevcut kayıtları geçmişe alınacak ve tüm aktif hasta alanları temizlenecek. Devam edilsin mi?'
        : 'Tüm aktif hasta alanları temizlenip boş bir hasta kaydı açılsın mı?',
    );
    if (!confirmed) return;

    startNewPatientSession();
    navigate('/analysis/mock', { replace: true });
  }

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 px-4 py-4 backdrop-blur sm:px-6 lg:px-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-950">MediCore AI</h1>
          <p className="mt-1 text-sm text-slate-500">Klinik değerlendirme sistemi</p>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <button
            type="button"
            onClick={handleResetPatient}
            className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm font-semibold text-blue-700 transition hover:bg-blue-100"
          >
            Hastayı kaydet ve temizle
          </button>

          <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 sm:justify-start">
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
