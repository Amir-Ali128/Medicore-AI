import { FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import {
  getStoredUser,
  isAuthenticated,
  login,
  logout,
} from '../services/authClient';

export default function AdminLoginPage() {
  const navigate = useNavigate();
  const [nickname, setNickname] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    // Do not redirect from a stale localStorage user record. A valid JWT is
    // required; otherwise the old behavior could bounce between login/routes.
    if (isAuthenticated() && getStoredUser()?.role === 'admin') {
      navigate('/admin/analytics', { replace: true });
    }
  }, [navigate]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setIsSubmitting(true);
      setError('');

      const user = await login(nickname, password, 'institutional');
      if (user.role !== 'admin') {
        logout();
        throw new Error('Bu hesap yönetici yetkisine sahip değil.');
      }

      navigate('/admin/analytics', { replace: true });
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'Yönetici girişi yapılamadı.',
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-10">
      <div className="w-full max-w-md rounded-3xl border border-slate-800 bg-white p-8 shadow-2xl sm:p-10">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-600 text-xl font-bold text-white">
            M
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-700">
              MediCore AI
            </p>
            <h1 className="mt-1 text-2xl font-semibold text-slate-950">Yönetici paneli</h1>
          </div>
        </div>

        <p className="mt-5 text-sm leading-6 text-slate-500">
          Canlı trafik, AI kullanım maliyeti ve yönetim ekranları yalnızca geçerli yönetici oturumuyla görüntülenebilir.
        </p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-5">
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Yönetici rumuzu</span>
            <input
              type="text"
              value={nickname}
              onChange={(event) => setNickname(event.target.value)}
              required
              minLength={3}
              maxLength={32}
              autoCapitalize="none"
              autoComplete="username"
              spellCheck={false}
              className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-cyan-400 focus:ring-4 focus:ring-cyan-100"
              placeholder="admin"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-slate-700">Şifre</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              autoComplete="current-password"
              className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-cyan-400 focus:ring-4 focus:ring-cyan-100"
              placeholder="Yönetici şifresi"
            />
          </label>

          {error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? 'Kontrol ediliyor…' : 'Yönetici olarak giriş yap'}
          </button>
        </form>

        <div className="mt-6 border-t border-slate-100 pt-5 text-center">
          <Link
            to="/login"
            className="text-sm font-semibold text-cyan-700 hover:text-cyan-800"
          >
            ← Bireysel / kurumsal giriş
          </Link>
        </div>
      </div>
    </main>
  );
}
