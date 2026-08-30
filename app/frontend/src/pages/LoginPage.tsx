import { FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import {
  getStoredUser,
  isAuthenticated,
  login,
  register,
  type AccountType,
  type AuthUser,
} from '../services/authClient';

type AuthMode = 'login' | 'register';

function destinationForUser(user: AuthUser) {
  if (user.role === 'admin') return '/admin/analytics';
  if (user.role === 'patient') return '/patients/demo';
  return '/analysis/mock';
}

export default function LoginPage() {
  const navigate = useNavigate();

  const [accountType, setAccountType] = useState<AccountType>('individual');
  const [mode, setMode] = useState<AuthMode>('login');
  const [nickname, setNickname] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  const isIndividual = accountType === 'individual';
  const isRegister = isIndividual && mode === 'register';

  useEffect(() => {
    if (!isAuthenticated()) return;
    const user = getStoredUser();
    if (user) navigate(destinationForUser(user), { replace: true });
  }, [navigate]);

  function changeAccountType(nextType: AccountType) {
    setAccountType(nextType);
    setMode('login');
    setNickname('');
    setPassword('');
    setConfirmPassword('');
    setError('');
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setIsSubmitting(true);
      setError('');

      if (isRegister) {
        if (password !== confirmPassword) {
          throw new Error('Şifreler aynı değil.');
        }

        const user = await register({ nickname, password });
        navigate(destinationForUser(user), { replace: true });
        return;
      }

      const user = await login(nickname, password, accountType);
      navigate(destinationForUser(user), { replace: true });
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
    setAccountType('institutional');
    setMode('login');
    setNickname('doctor');
    setPassword('demo123');
    setConfirmPassword('');
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
              Sağlık verisine daha sade ve mahremiyet odaklı erişim
            </h1>

            <p className="mt-4 text-sm leading-6 text-slate-300">
              Bireysel hesaplarda ad-soyad ve e-posta istemeden yalnızca rumuz ve
              şifre ile hesap oluşturulur. Kurumsal hesaplar kurum tarafından
              tanımlanır.
            </p>

            <div className="mt-8 rounded-2xl border border-blue-400/30 bg-blue-500/10 p-4">
              <p className="text-sm leading-6 text-blue-100">
                Doktor ve laboratuvar hesapları herkese açık kayıt ekranından
                oluşturulmaz. Yetkiler kurum tarafından belirlenir.
              </p>
            </div>
          </section>

          <section className="p-8 sm:p-10">
            <div className="grid grid-cols-2 rounded-2xl border border-slate-200 bg-slate-50 p-1">
              <button
                type="button"
                onClick={() => changeAccountType('individual')}
                className={`rounded-xl px-4 py-3 text-sm font-semibold transition ${
                  isIndividual
                    ? 'bg-white text-slate-950 shadow-sm'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                Bireysel
              </button>

              <button
                type="button"
                onClick={() => changeAccountType('institutional')}
                className={`rounded-xl px-4 py-3 text-sm font-semibold transition ${
                  !isIndividual
                    ? 'bg-white text-slate-950 shadow-sm'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                Kurumsal
              </button>
            </div>

            {isIndividual ? (
              <div className="mt-4 flex rounded-2xl border border-slate-200 bg-slate-50 p-1">
                <button
                  type="button"
                  onClick={() => {
                    setMode('login');
                    setError('');
                  }}
                  className={`flex-1 rounded-xl px-4 py-2 text-sm font-semibold transition ${
                    mode === 'login'
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
                    setPassword('');
                    setConfirmPassword('');
                    setError('');
                  }}
                  className={`flex-1 rounded-xl px-4 py-2 text-sm font-semibold transition ${
                    mode === 'register'
                      ? 'bg-white text-slate-950 shadow-sm'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  Hesap oluştur
                </button>
              </div>
            ) : null}

            <div className="mt-8">
              <p className="text-sm font-semibold uppercase text-blue-700">
                {isIndividual ? 'Bireysel kullanıcı' : 'Kurumsal kullanıcı'}
              </p>

              <h2 className="mt-2 text-2xl font-semibold text-slate-950">
                {isRegister
                  ? 'Bireysel hesap oluştur'
                  : isIndividual
                    ? 'Bireysel giriş'
                    : 'Kurumsal giriş'}
              </h2>

              <p className="mt-2 text-sm leading-6 text-slate-500">
                {isRegister
                  ? 'Sadece bir rumuz ve şifre belirle. Gerçek ad veya e-posta istenmez.'
                  : isIndividual
                    ? 'Rumuzun ve şifren ile hesabına giriş yap.'
                    : 'Doktor ve laboratuvar hesapları kurum tarafından tanımlanır. Yönetici hesabı için ayrı yönetici girişini de kullanabilirsin.'}
              </p>
            </div>

            <form onSubmit={handleSubmit} className="mt-8 space-y-5">
              <label className="block">
                <span className="text-sm font-medium text-slate-700">
                  Rumuz (Nickname)
                </span>
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
                  className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
                  placeholder={isIndividual ? 'Örn. nightfox27' : 'Örn. dr.ayse'}
                />
                {isRegister ? (
                  <span className="mt-2 block text-xs leading-5 text-slate-500">
                    3-32 karakter; harf, rakam, nokta, alt çizgi ve tire kullanılabilir.
                  </span>
                ) : null}
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
                  minLength={isRegister ? 6 : 1}
                  autoComplete={isRegister ? 'new-password' : 'current-password'}
                  className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
                  placeholder={isRegister ? 'En az 6 karakter' : 'Şifren'}
                />
              </label>

              {isRegister ? (
                <label className="block">
                  <span className="text-sm font-medium text-slate-700">
                    Şifre tekrar
                  </span>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    required
                    minLength={6}
                    autoComplete="new-password"
                    className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
                    placeholder="Şifreyi tekrar yaz"
                  />
                </label>
              ) : null}

              {error ? (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-700">
                  {error}
                </div>
              ) : null}

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

              {!isIndividual ? (
                <button
                  type="button"
                  onClick={fillDemoDoctor}
                  className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-blue-200 hover:bg-blue-50"
                >
                  Demo doktor bilgilerini doldur
                </button>
              ) : null}
            </form>

            <div className="mt-6 border-t border-slate-100 pt-5 text-center">
              <Link
                to="/admin/login"
                className="text-sm font-semibold text-cyan-700 hover:text-cyan-800"
              >
                Yönetici girişi →
              </Link>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
