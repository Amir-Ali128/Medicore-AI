import { Link, useLocation, useNavigate } from 'react-router-dom';

const LEGAL_ACK_KEY = 'medicore:legalWarningsAcknowledged:v1';

type GateState = {
  acknowledgementRequired?: boolean;
  from?: {
    pathname?: string;
    search?: string;
  };
} | null;

export default function HomePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const gateState = location.state as GateState;
  const needsAcknowledgement = gateState?.acknowledgementRequired === true;

  function acknowledgeAndContinue() {
    localStorage.setItem(LEGAL_ACK_KEY, 'true');

    const pathname = gateState?.from?.pathname || '/case';
    const search = gateState?.from?.search || '';
    navigate(`${pathname}${search}`, { replace: true });
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {needsAcknowledgement ? (
        <section className="rounded-[28px] border border-amber-300 bg-amber-50 p-6 shadow-sm sm:p-8">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-amber-700">
            Klinik kullanım uyarısı
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
            MediCore klinik karar desteği sağlar.
          </h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-700">
            Sistem kesin tanı veya tedavi kararı vermez ve hekim değerlendirmesinin yerine geçmez.
            Kaynak veriler, AI çıktıları ve önerilen ileri değerlendirmeler hekim tarafından doğrulanmalıdır.
          </p>
          <button
            type="button"
            onClick={acknowledgeAndContinue}
            className="mt-5 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800"
          >
            Anladım, devam et
          </button>
        </section>
      ) : null}

      <section className="overflow-hidden rounded-[32px] bg-slate-950 p-6 text-white shadow-sm sm:p-9 lg:p-12">
        <div className="grid gap-10 lg:grid-cols-[1.25fr_0.75fr] lg:items-end">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-300">
              MediCore AI
            </p>
            <h1 className="mt-4 max-w-3xl text-4xl font-semibold tracking-[-0.04em] sm:text-5xl lg:text-6xl">
              Bir vaka. Üç veri kaynağı. Tek çalışma alanı.
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300">
              Klinik bilgiler, laboratuvar sonuçları ve EKG/EKO/USG/BT/MR/röntgen gibi tetkik raporlarını tek yerde birleştir.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link
                to="/case"
                className="rounded-2xl bg-white px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-slate-100"
              >
                Yeni vaka oluştur
              </Link>
              <Link
                to="/history"
                className="rounded-2xl border border-white/15 px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/10"
              >
                Geçmişi aç
              </Link>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            {[
              ['01', 'Klinik', 'Şikayet, öykü, ilaçlar'],
              ['02', 'Lab', 'Sonuç + rapordaki referans'],
              ['03', 'Rapor', 'Tüm tetkikler tek formatta'],
            ].map(([number, title, text]) => (
              <div key={number} className="rounded-3xl border border-white/10 bg-white/5 p-4 backdrop-blur">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-bold text-blue-300">{number}</span>
                  <p className="font-semibold">{title}</p>
                </div>
                <p className="mt-2 text-sm text-slate-400">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {[
          ['Kaynak sadakati', 'Lab referansları rapordan alınır; sistem eksik referans uydurmaz.'],
          ['Sınıflandırma yok', 'Normal / abnormal / high / low gibi otomatik sınıflandırma katmanı yok.'],
          ['Tek rapor modeli', 'EKG’den tomografiye kadar tüm yazılı tetkik raporları aynı vaka içinde tutulur.'],
        ].map(([title, text]) => (
          <div key={title} className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-4 h-2 w-10 rounded-full bg-blue-600" />
            <h2 className="text-lg font-semibold tracking-tight text-slate-950">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">{text}</p>
          </div>
        ))}
      </section>

      <section className="rounded-[28px] border border-amber-200 bg-amber-50 px-5 py-4">
        <p className="text-sm leading-6 text-amber-900">
          MediCore klinik karar desteği sağlar; kesin tanı veya tedavi kararı vermez ve hekim değerlendirmesinin yerine geçmez.
        </p>
      </section>
    </div>
  );
}
