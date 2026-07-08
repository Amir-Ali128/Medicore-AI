import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  login,
  register,
  type UserRole,
} from '../services/authClient';

type AuthMode = 'login' | 'register';

export default function LoginPage() {
  const navigate = useNavigate();

  const [mode, setMode] = useState<AuthMode>('login');
  const [fullName, setFullName] = useState('Demo Doctor');
  const [email, setEmail] = useState('doctor@medicore.ai');
  const [password, setPassword] = useState('demo123');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [role, setRole] = useState<UserRole>('doctor');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  const isRegister = mode === 'register';

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setIsSubmitting(true);
      setError('');

      if (isRegister) {
        if (password !== confirmPassword) {
          throw new Error('Şifreler aynı değil.');
        }

        await register({
          full_name: fullName,
          email,
          password,
          role,
        });
      } else {
        await login(email, password);
      }

      navigate('/analysis/mock');
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'İşlem tamamlanamadı.',
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  function fillDemoDoctor() {
    setMode('login');
    setFullName('Demo Doctor');
    setEmail('doctor@medicore.ai');
    setPassword('demo123');
    setConfirmPassword('');
    setRole('doctor');
    setError('');
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-5xl overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xl">
        <div className="grid lg:grid-cols-[0.9fr_1.1fr]">
          <section className="bg-slate-950 p-8 text-white sm:p-10">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600 text-2xl font-bold">
              M
            </div>

            <p className="mt-8 text-sm font-semibold uppercase tracking-[0.2em] text-blue-200">
              MediCore AI
            </p>

            <h1 className="mt-3 text-3xl font-semibold leading-tight">
              Physician-reviewed lab intelligence
            </h1>

            <p className="mt-4 text-sm leading-6 text-slate-300">
              PDF laboratuvar sonuçlarını yapılandırır, anormal değerleri işaretler
              ve doktor incelemesi için güvenli klinik özet üretir.
            </p>

            <div className="mt-8 rounded-2xl border border-blue-400/30 bg-blue-500/10 p-4">
              <p className="text-sm leading-6 text-blue-100">
                Klinik çıktılar doktor incelemesi için yapılandırılmıştır; tanı veya
                tedavi önerisi değildir.
              </p>
            </div>
          </section>

          <section className="p-8 sm:p-10">
            <div className="flex rounded-2xl border border-slate-200 bg-slate-50 p-1">
              <button
                type="button"
                onClick={() => {
                  setMode('login');
                  setError('');
                }}
                className={`flex-1 rounded-xl px-4 py-2 text-sm font-semibold transition ${
                  !isRegister
                    ? 'bg-white text-slate-950 shadow-sm'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                Giriş yap
              </button>

              <button
                type="button"
                onClick={() => {
                  setMode('register');
                  setError('');

                  if (email === 'doctor@medicore.ai') {
                    setEmail('');
                    setPassword('');
                  }
                }}
                className={`flex-1 rounded-xl px-4 py-2 text-sm font-semibold transition ${
                  isRegister
                    ? 'bg-white text-slate-950 shadow-sm'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                Hesap oluştur
              </button>
            </div>

            <div className="mt-8">
              <p className="text-sm font-semibold uppercase text-blue-700">
                {isRegister ? 'Yeni kullanıcı' : 'Demo login'}
              </p>

              <h2 className="mt-2 text-2xl font-semibold text-slate-950">
                {isRegister ? 'Hesap oluştur' : 'Hesabına giriş yap'}
              </h2>

              <p className="mt-2 text-sm leading-6 text-slate-500">
                {isRegister
                  ? 'Demo/pilot kullanıcıları için hızlı kayıt. Production’da doktor kaydı davet/onay sistemiyle sınırlandırılmalı.'
                  : 'Demo doktor hesabı ile giriş yapabilir veya yeni hesap oluşturabilirsin.'}
              </p>
            </div>

            <form onSubmit={handleSubmit} className="mt-8 space-y-5">
              {isRegister && (
                <label className="block">
                  <span className="text-sm font-medium text-slate-700">
                    Ad soyad
                  </span>
                  <input
                    type="text"
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                    required
                    minLength={2}
                    className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
                    placeholder="Dr. Ayşe Yılmaz"
                  />
                </label>
              )}

              <label className="block">
                <span className="text-sm font-medium text-slate-700">
                  E-posta
                </span>
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
                  placeholder="doctor@medicore.ai"
                />
              </label>

              <label className="block">
                <span className="text-sm font-medium text-slate-700">
                  Şifre
                </span>
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  minLength={6}
                  className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
                  placeholder="En az 6 karakter"
                />
              </label>

              {isRegister && (
                <>
                  <label className="block">
                    <span className="text-sm font-medium text-slate-700">
                      Şifre tekrar
                    </span>
                    <input
                      type="password"
                      value={confirmPassword}
                      onChange={(event) =>
                        setConfirmPassword(event.target.value)
                      }
                      required
                      minLength={6}
                      className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
                      placeholder="Şifreyi tekrar yaz"
                    />
                  </label>

                  <label className="block">
                    <span className="text-sm font-medium text-slate-700">
                      Rol
                    </span>
                    <select
                      value={role}
                      onChange={(event) =>
                        setRole(event.target.value as UserRole)
                      }
                      className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
                    >
                      <option value="doctor">Doktor / klinisyen</option>
                      <option value="lab_staff">Laboratuvar görevlisi</option>
                      <option value="patient">Hasta</option>
                    </select>
                  </label>
                </>
              )}

              {error && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-700">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full rounded-xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSubmitting
                  ? isRegister
                    ? 'Hesap oluşturuluyor...'
                    : 'Giriş yapılıyor...'
                  : isRegister
                    ? 'Hesap oluştur ve giriş yap'
                    : 'Giriş yap'}
              </button>

              {!isRegister && (
                <button
                  type="button"
                  onClick={fillDemoDoctor}
                  className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-blue-200 hover:bg-blue-50"
                >
                  Demo doktor bilgilerini doldur
                </button>
              )}
            </form>
          </section>
        </div>
      </div>
    </main>
  );
}