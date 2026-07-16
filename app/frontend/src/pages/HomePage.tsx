import { Link } from 'react-router-dom';

const workflowCards = [
  {
    title: 'Hasta Bilgileri',
    description:
      'Cinsiyet, yaş, boy, kilo, kişisel ve ailesel hastalıklar, kalıtsal durumlar, ameliyatlar ve kullanılan ilaçlar gibi klinik bilgileri girin veya güncelleyin.',
    to: '/patients/demo',
    icon: '👤',
    className: 'border-blue-200 bg-blue-50 text-blue-900 hover:bg-blue-100',
  },
  {
    title: 'Laboratuvar Tetkikleri',
    description:
      'Mevcut laboratuvar sonuçlarını sisteme aktarın, kaydedin ve tetkik analizini başlatın.',
    to: '/analysis/mock',
    icon: '🩸',
    className:
      'border-rose-200 bg-rose-50 text-rose-900 hover:bg-rose-100',
  },
  {
    title: 'Radyoloji ve Tetkik Raporları',
    description:
      'Radyoloji, endoskopi ve diğer tanısal tetkik raporlarını sisteme ekleyin, görüntüleyin ve değerlendirin.',
    to: '/radiology',
    icon: '🩻',
    className:
      'border-cyan-200 bg-cyan-50 text-cyan-900 hover:bg-cyan-100',
  },
];

export default function HomePage() {
  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">
          Medicore AI
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">
          Klinik Değerlendirme ve Karar Destek Sistemi
        </h1>
        <p className="mt-3 max-w-4xl text-sm leading-7 text-slate-600">
          Bu sistem; bireyin veya hastanın cinsiyet, yaş, boy ve kilo bilgileri ile
          kişisel ve ailesel hastalıklar, ameliyatlar ve kullanılan ilaçlar gibi öz
          geçmiş ve soy geçmiş bilgilerini; laboratuvar, radyoloji, endoskopi ve
          benzeri tetkik bulgularıyla birlikte yorumlayarak olası hastalıkların
          saptanması, bilinen hastalıkların gidişatının değerlendirilmesi ve uygun
          bir yol haritası oluşturulması hakkında bilgilendirme sağlamayı
          amaçlamaktadır.
        </p>
      </header>

      <section className="rounded-xl border border-amber-200 bg-amber-50 p-5">
        <h2 className="text-base font-semibold text-amber-950">
          Yasal bilgilendirme
        </h2>
        <p className="mt-2 text-sm leading-7 text-amber-900">
          Sistemde sunulan tüm değerlendirme ve öneriler yalnızca tavsiye ve
          bilgilendirme amaçlıdır. Doktorunuza danışmadan tetkik yaptırma, ilaç
          dozunu değiştirme, ilaç bırakma veya yeni bir ilaç kullanma gibi herhangi
          bir tıbbi eylemde bulunmayınız. Nihai değerlendirme ve tedavi kararı
          hekiminize aittir.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-semibold text-slate-950">Nasıl kullanacaksınız?</h2>

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-base font-semibold text-slate-950">
              A. İlk defa giriş yapanlar
            </h3>
            <ol className="mt-3 list-decimal space-y-3 pl-5 text-sm leading-7 text-slate-600">
              <li>
                <strong className="text-slate-900">Hasta Bilgileri</strong>
                {' '}ekranından kendinize ve ailenize ait sağlık bilgilerini girin.
              </li>
              <li>
                Laboratuvar, radyoloji ve diğer bulgulara ait mevcut sonuçları
                ilgili bölümlere aktarın. Veri girişini tamamladıktan sonra tetkik
                analizini başlatın ve işlemin tamamlanmasını bekleyin.
              </li>
              <li>
                Analiz sonuçlarını, klinik yorumları ve önerileri sırasıyla
                inceleyin.
              </li>
            </ol>
          </article>

          <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-base font-semibold text-slate-950">
              B. Tekrar giriş yapanlar
            </h3>
            <p className="mt-3 text-sm leading-7 text-slate-600">
              Önceki sıralamayı takip ederek değişen bilgileri ilgili alanlarda
              güncelleyin. İlaç veya doz değişikliği, yeni başlanan ilaçlar, yeni
              tanılar, geçirilen ameliyatlar ve yeni tetkik sonuçları gibi bilgileri
              kaydettikten sonra analiz ve değerlendirme adımlarına devam edin.
            </p>
          </article>
        </div>
      </section>

      <section>
        <h2 className="text-xl font-semibold text-slate-950">İşleme başlayın</h2>
        <p className="mt-2 text-sm text-slate-500">
          Devam etmek istediğiniz bölümü seçin.
        </p>

        <div className="mt-4 grid gap-4 md:grid-cols-3">
          {workflowCards.map((card) => (
            <Link
              key={card.to}
              to={card.to}
              className={`rounded-xl border p-5 transition ${card.className}`}
            >
              <span className="text-2xl" aria-hidden="true">
                {card.icon}
              </span>
              <h3 className="mt-4 text-lg font-semibold">{card.title}</h3>
              <p className="mt-2 text-sm leading-6 opacity-80">
                {card.description}
              </p>
              <p className="mt-4 text-sm font-semibold">Bölümü aç →</p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
